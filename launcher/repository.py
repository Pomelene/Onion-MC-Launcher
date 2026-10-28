# -*- coding: utf-8 -*-
"""游戏仓库：游戏目录结构、版本安装与资源路径管理。

一次安装包含：版本 JSON（含继承链）、客户端 jar、库、资源对象、
日志配置与原生库解压；同时提供版本隔离下的实例目录。
"""

import json
import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from .assets import AssetIndex, ensure_virtual_assets
from .config import Config
from .download import DownloadError, DownloadJob, Downloader, sha1_of
from .natives import extract_all_natives, extract_all_natives_from
from .rules import os_name
from .safety import child, contained, recycle, write_text
from .sources import MOJANG, MOJANG_MANIFEST, DownloadSource, make_source
from .version import (ResolvedVersion, VersionEntry, VersionManifest,
                      VersionNotFound, VersionResolver)

#: 进度回调：(阶段文字) / (已完成, 总数)
StageCallback = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[int, int], None]]


class GameRepository:
    """管理一个游戏目录（相当于 .minecraft）。"""

    def __init__(self, config: Config, downloader: Optional[Downloader] = None):
        self.config = config
        self.game_dir = config.game_dir()
        self.versions_dir = self.game_dir / "versions"
        self.libraries_dir = self.game_dir / "libraries"
        self.assets_dir = self.game_dir / "assets"
        proxy = ""
        if config.get("proxy_host"):
            proxy = f"http://{config.get('proxy_host')}:{config.get('proxy_port')}"
        self.downloader = downloader or Downloader(
            threads=int(config.get("max_download_threads") or 8), proxy=proxy or None,
            speed_limit=int(config.get("download_speed_limit") or 0))
        self.source: DownloadSource = make_source(config.get("download_source") or "mojang")
        self.resolver = VersionResolver(self.versions_dir)
        self._manifest: Optional[VersionManifest] = None
        # 只读参考目录（例如 F:\.minecraft）：仅用于填补缺失的库/资源，绝不写入
        self.fallback_roots: list[Path] = []
        for raw in (config.get("reference_roots") or []):
            root = Path(str(raw)).expanduser()
            try:
                if root.is_dir() and root.resolve() != self.game_dir.resolve():
                    self.fallback_roots.append(root)
            except OSError:
                continue
        self.downloader.write_guard = self._guard_download

    def _guard_download(self, path: Path) -> None:
        # Java runtime downloads can live beside the launcher. Game downloads are confined
        # to the selected root, including lexical paths containing '..'.
        for root in (self.game_dir, *self.fallback_roots):
            try:
                Path(path).absolute().relative_to(root.absolute())
            except ValueError:
                continue
            self.assert_writable(path)
            return

    # ------------------------------------------------------------------ 路径

    def remap(self, url: str) -> str:
        return self.source.remap(url)

    def cache_path(self, *parts) -> Path:
        from .paths import cache_dir
        from .storage import _hide
        path=self.assert_writable(child(cache_dir(self.game_dir),str(Path(*parts))))
        path.parent.mkdir(parents=True,exist_ok=True);_hide(self.game_dir/'.onion')
        return path

    # ------------------------------------------------------------ 只读回退

    def readonly_roots(self) -> list[Path]:
        """所有只读参考根（不会被写入）。"""
        return list(self.fallback_roots)

    def _in_readonly_root(self, path: Path) -> bool:
        """path 是否落在某个只读参考根内。"""
        try:
            resolved = Path(path).resolve()
        except OSError:
            return False
        for root in self.fallback_roots:
            try:
                resolved.relative_to(root.resolve())
                return True
            except (ValueError, OSError):
                continue
        return False

    def assert_writable(self, path: Path) -> Path:
        """写入闸门：禁止把任何内容写进只读参考目录。"""
        if self.fallback_roots and self._in_readonly_root(path):
            raise PermissionError(f"拒绝写入只读参考目录：{path}")
        return contained(path, self.game_dir)

    def invalidate_library_cache(self) -> None:
        """安装/删除/解压后调用：让库路径缓存失效。"""
        self._lib_resolve_cache = {}

    def assert_idle(self, version_id: str) -> None:
        from .launch import _pid_alive
        lock = self.version_dir(version_id) / ".instance.lock"
        if lock.exists():
            try:
                pid = int(lock.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise RuntimeError("无法确认实例状态，请先确认游戏已关闭") from exc
            if _pid_alive(pid):
                raise RuntimeError("实例正在运行，请先关闭游戏再修改文件")

    def resolve_library_file(self, lib) -> tuple[Optional[Path], str]:
        """定位库文件，返回 (路径, 来源)；来源为 workspace / reference / missing。

        结果按 (name, is_native) 记忆化：一次启动会重复查询同一批库（构建 classpath、
        校验、解压原生库），实测可省掉大部分重复 stat。
        """
        cache = getattr(self, "_lib_resolve_cache", None)
        if cache is None:
            cache = {}
            self._lib_resolve_cache = cache
        key = (lib.name, lib.is_native())
        cached = cache.get(key)
        if cached is not None:
            return cached
        rel = lib.native_path() if lib.is_native() else lib.artifact_path()
        if not rel:
            result: tuple[Optional[Path], str] = (None, "missing")
            cache[key] = result
            return result
        local = child(self.libraries_dir, rel)
        if local.is_file():
            result = (local, "workspace")
        else:
            result = (None, "missing")
            for root in self.fallback_roots:
                candidate = root / "libraries" / rel
                if candidate.is_file():
                    result = (candidate, "reference")
                    break
        cache[key] = result
        return result

    def _reference_covers_index(self, index_path: Path, assets_root: Path, expected=None) -> bool:
        """Recheck directory contents; a previous hit cannot hide removed assets."""
        try:
            size=Path(index_path).stat().st_size
            if size>32*1024**2:return False
            if expected:
                if expected.get('size') is not None and size!=expected['size']:return False
                if expected.get('sha1') and sha1_of(index_path)!=str(expected['sha1']).lower():return False
            index=AssetIndex.parse(json.loads(Path(index_path).read_text(encoding='utf-8')))
            return not index.jobs(Path(assets_root)/'objects')
        except (OSError,ValueError,KeyError,TypeError,AttributeError):return False

    def reference_assets_dir(self) -> Optional[Path]:
        """可作为只读 --assetsDir 的参考资源目录（需同时存在 indexes 与 objects）。"""
        for root in self.fallback_roots:
            assets = root / "assets"
            if (assets / "indexes").is_dir() and (assets / "objects").is_dir():
                return assets
        return None

    def version_dir(self, version_id: str) -> Path:
        return child(self.versions_dir, version_id)

    def client_jar_path(self, rv: ResolvedVersion) -> Path:
        """客户端 jar 的位置。

        优先级：JSON 的 jar 字段 > 本版本目录自带的 <id>.jar > 继承来的原版 jar。
        像 OptiFine / 旧版 Forge 这类“自带补丁 jar”的版本必须用自己目录里的那份；
        而纯加载器（Fabric/Forge）没有自己的 jar，只能用原版 jar。
        """
        jar_id = getattr(rv, "jar_id", "") or ""
        if jar_id:
            return self.version_dir(jar_id) / f"{jar_id}.jar"
        own = self.version_dir(rv.id) / f"{rv.id}.jar"
        if own.is_file():
            return own
        vid = rv.client_version_id or rv.id
        return self.version_dir(vid) / f"{vid}.jar"

    def run_dir(self, version_id: str) -> Path:
        """游戏运行目录。

        三种情况：该版本带 .isolate 标记（整合包）> 全局版本隔离 > 游戏根目录。
        """
        instance = self.version_dir(version_id)
        from .version_settings import VersionSettingsStore
        from .storage import is_portable
        settings_path=self.config.path if is_portable(self.config.path) else self.config.path.parent/"version_settings.json"
        legacy=self.config.get('library_legacy_root')
        overrides = VersionSettingsStore(settings_path,self.game_dir if legacy else None,legacy or None).get(version_id)
        isolated = overrides.get("isolate", self.config.get("version_isolation"))
        if "isolate" not in overrides and any((instance / d).is_dir() for d in ("mods", "saves", "config")):
            isolated = True
        if (instance / ".isolate").exists() or isolated:
            return instance
        return self.game_dir

    def _instance_sub(self, version_id: str, sub: str) -> Path:
        """资源子目录：run_dir 本身已按隔离策略解析。"""
        return self.run_dir(version_id) / sub

    def mods_dir(self, version_id: str) -> Path:
        return self._instance_sub(version_id, "mods")

    def resourcepacks_dir(self, version_id: str) -> Path:
        return self._instance_sub(version_id, "resourcepacks")

    def shaderpacks_dir(self, version_id: str) -> Path:
        return self._instance_sub(version_id, "shaderpacks")

    def saves_dir(self, version_id: str) -> Path:
        return self._instance_sub(version_id, "saves")

    def logs_dir(self, version_id: str) -> Path:
        return self.run_dir(version_id) / "logs"

    def natives_dir(self, version_id: str) -> Path:
        return self.version_dir(version_id) / f"natives-{os_name()}"

    # ------------------------------------------------------------------ 清单

    def fetch_manifest(self, force: bool = False) -> VersionManifest:
        if self._manifest is not None and not force:
            return self._manifest
        try:
            data = self.downloader.fetch_json(self.source.version_manifest_url())
        except DownloadError:
            # 镜像清单不可用时回退官方
            if self.source.name != MOJANG:
                data = self.downloader.fetch_json(MOJANG_MANIFEST)
            else:
                raise
        self._manifest = VersionManifest(data)
        return self._manifest

    def list_installed(self) -> list[str]:
        return self.resolver.list_installed()

    def version_summary(self, version_id: str) -> dict:
        """读取本地版本 JSON 的概要信息（用于列表显示）。"""
        try:
            data = self.resolver.load_raw(version_id)
        except Exception:  # noqa: BLE001
            return {"id": version_id, "type": "unknown", "release_time": ""}
        return {"id": version_id, "type": data.get("type", "unknown"),
                "release_time": data.get("releaseTime", "")}

    def loader_label(self, version_id: str) -> str:
        from .modpack import _detect_loader
        try:
            resolved = self.resolver.resolve(version_id)
            if any(lib.name.lower().startswith("optifine:") for lib in resolved.libraries):
                return "OptiFine"
            name, _version = _detect_loader(self, version_id)
            return {"fabric": "Fabric", "legacyfabric":"Legacy Fabric", "quilt": "Quilt", "forge": "Forge",
                    "neoforge": "NeoForge"}.get(name, "原版")
        except (OSError, ValueError):
            return "未知"

    # ------------------------------------------------------------------ 安装

    def install(self, version_id: str, on_stage: StageCallback = None,
                on_progress: ProgressCallback = None,
                features: Optional[dict] = None) -> ResolvedVersion:
        """安装（或补全）一个版本，返回解析后的版本信息。"""
        def stage(text: str) -> None:
            if on_stage:
                on_stage(text)

        self.invalidate_library_cache()
        self.assert_writable(self.version_dir(version_id))
        self.assert_idle(version_id)
        local = self.resolver.json_path(version_id).exists()
        # Installed instances launch offline; a manifest is needed only for missing parents.
        manifest = None
        entry = None
        if not local:
            manifest = self.fetch_manifest()
            entry = manifest.find(version_id)
        if entry is None and not local:
            raise VersionNotFound(version_id)

        stage(f"读取本地版本信息 · {version_id}" if local else f"获取 {version_id} 版本信息")
        if entry is not None:
            self._download_version_chain(entry, manifest)
        try:
            rv = self.resolver.resolve(version_id, features)
        except VersionNotFound as exc:
            manifest = manifest or self.fetch_manifest()
            raw = self.resolver.load_raw(version_id)
            parent = manifest.find(raw.get("inheritsFrom", ""))
            if parent is None:
                raise exc
            self._download_version_chain(parent, manifest)
            rv = self.resolver.resolve(version_id, features)

        stage("检查客户端文件")
        if rv.java_major is None:
            from .foreign import detect_mod_java_requirement
            rv.java_major = detect_mod_java_requirement(self.mods_dir(version_id)) or 8
        self._ensure_client(rv)

        stage("检查本地依赖库")
        self._ensure_libraries(rv, features, on_progress, on_stage)

        stage("检查本地资源")
        self._ensure_assets(rv, on_progress, on_stage)

        stage("准备日志配置")
        self._ensure_logging(rv)

        stage("解压原生库")
        self.ensure_natives(rv, features)

        stage("游戏文件已就绪")
        return rv

    def _download_version_chain(self, entry: VersionEntry,
                                manifest: VersionManifest) -> None:
        """下载版本 JSON 及其父版本 JSON（已存在则跳过）。"""
        cur: Optional[VersionEntry] = entry
        guard = 0
        while cur is not None and guard < 20:
            guard += 1
            path = self.resolver.json_path(cur.id)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                job = DownloadJob(self.remap(cur.url), path, name=f"{cur.id}.json", fallback_urls=(cur.url,))
                self.downloader.download_one(job)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                break
            parent_id = data.get("inheritsFrom")
            if not parent_id:
                break
            if self.resolver.json_path(parent_id).exists():
                cur = VersionEntry(parent_id, "release", "")  # 已存在，下一步只读
                break
            parent_entry = manifest.find(parent_id)
            if parent_entry is not None:
                cur = parent_entry
                continue
            # 清单中找不到时尝试按 id 直接抓取（镜像兜底）
            fallback = self.resolver.json_path(parent_id)
            try:
                text = self.downloader.fetch(self.source.version_json_url(parent_id))
                fallback.parent.mkdir(parents=True, exist_ok=True)
                write_text(self.assert_writable(fallback), text)
            except Exception:  # noqa: BLE001
                pass
            break

    def _ensure_client(self, rv: ResolvedVersion) -> None:
        client = rv.client or {}
        url = client.get("url")
        if not url:
            return
        path = self.client_jar_path(rv)
        # A loader's own patched jar must not be replaced with its inherited vanilla jar.
        if path.exists() and (self.config.get("foreign_mode") or
                path.parent.name != (rv.client_version_id or rv.id)):
            return
        job = DownloadJob(self.remap(url), path, sha1=client.get("sha1"),
                          size=client.get("size"), name=path.name, fallback_urls=(url,))
        self.assert_writable(path)
        self.downloader.download_one(job)

    def _ensure_libraries(self, rv: ResolvedVersion, features: Optional[dict] = None,
                          on_progress: ProgressCallback = None, on_stage: StageCallback = None) -> None:
        jobs: list[DownloadJob] = []
        for lib in rv.libraries:
            if not lib.matches(features):
                continue
            existing, _origin = self.resolve_library_file(lib)
            if existing is not None:
                continue
            if lib.is_native():
                p = lib.native_file(self.libraries_dir)
                u = lib.native_url(self.remap)
                info = lib.native_download() or {}
                if p and u:
                    jobs.append(DownloadJob(u, p, sha1=info.get("sha1"),
                                            size=info.get("size"), name=lib.name,
                                            fallback_urls=(lib.native_url(),)))
            else:
                p = lib.artifact_file(self.libraries_dir)
                sha1, size = lib.artifact_info()
                jobs.append(DownloadJob(lib.artifact_url(self.remap), p, sha1=sha1,
                                        size=size, name=lib.name, fallback_urls=(lib.artifact_url(),)))
        if jobs:
            if on_stage:on_stage(f"补全缺失依赖库 · {len(jobs)} 个文件")
            self.download_jobs(jobs, on_progress)
            self.invalidate_library_cache()

    def _ensure_assets(self, rv: ResolvedVersion, on_progress: ProgressCallback = None, on_stage: StageCallback = None) -> None:
        info = rv.asset_index or {}
        if not info:
            return
        index_id = rv.asset_index_id
        index_path = child(self.assets_dir / "indexes", f"{index_id}.json")
        ref_assets = self.reference_assets_dir()
        if ref_assets is not None:
            ref_index = ref_assets / "indexes" / f"{index_id}.json"
            if ref_index.exists() and self._reference_covers_index(ref_index, ref_assets,info):
                if on_stage:on_stage("本地资源已完整 · 使用已有资源目录")
                return
        index=None;existed=index_path.exists()
        if existed:
            try:
                size=index_path.stat().st_size
                if size>32*1024**2 or (info.get('size') is not None and size!=info['size']):raise ValueError('资源索引大小无效')
                if info.get('sha1') and sha1_of(index_path)!=str(info['sha1']).lower():raise ValueError('资源索引摘要不符')
                index=AssetIndex.parse(json.loads(index_path.read_text(encoding='utf-8')),index_id,url=info.get('url',''))
            except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
        if index is None:
            url = info.get("url")
            if not url:
                raise DownloadError('资源索引缺失或损坏，且版本没有提供修复地址')
            if on_stage:on_stage('本地资源索引损坏 · 正在修复' if existed else '本地资源索引缺失 · 正在获取索引')
            self.assert_writable(index_path)
            # A malformed cache without a checksum must not be accepted as a
            # size-only hit; known metadata remains verified by the downloader.
            self.downloader.download_one(DownloadJob(self.remap(url),index_path,sha1=info.get('sha1'),size=info.get('size'),fallback_urls=(url,),force=existed,max_size=32*1024**2))
            try:index=AssetIndex.parse(json.loads(index_path.read_text(encoding='utf-8')),index_id,url=url)
            except (OSError,ValueError,KeyError,TypeError,AttributeError):raise DownloadError('资源索引格式无效，请检查下载源后重试') from None
        jobs = index.jobs(self.assets_dir / "objects", self.remap)
        if jobs:
            if on_stage:on_stage(f"补全缺失或大小不符的资源 · {len(jobs)} 个文件")
            self.download_jobs(jobs, on_progress)
        elif on_stage:on_stage("本地资源已完整 · 无需下载")
        ensure_virtual_assets(self.game_dir, index)

    def _ensure_logging(self, rv: ResolvedVersion) -> None:
        log = rv.logging or {}
        file_meta = log.get("file") or {}
        url = file_meta.get("url")
        if not url:
            return
        filename = file_meta.get("id") or "client-1.12.xml"
        if self.logging_config_path(rv) is not None:
            return
        path = child(self.assets_dir / "log_configs", filename)
        if not path.exists():
            job = DownloadJob(self.remap(url), path, sha1=file_meta.get("sha1"),
                              size=file_meta.get("size"), name=filename)
            self.downloader.download_one(job)

    def logging_config_path(self, rv: ResolvedVersion,
                            search_dir: Optional[Path] = None) -> Optional[Path]:
        file_meta = (rv.logging or {}).get("file") or {}
        filename = file_meta.get("id")
        if not filename:
            return None
        path = self.assets_dir / "log_configs" / filename
        if path.exists():
            return path
        if search_dir is not None:
            alt = Path(search_dir) / "log_configs" / filename
            if alt.exists():
                return alt
        for root in self.fallback_roots:
            alt = root / "assets" / "log_configs" / filename
            if alt.exists():
                return alt
        return None

    # ------------------------------------------------------------------ 原生库

    def ensure_natives(self, rv: ResolvedVersion, features: Optional[dict] = None) -> Path:
        """解压原生库到版本目录下的 natives-<os>，返回该目录。"""
        natives_dir = self.natives_dir(rv.id)
        self.assert_writable(natives_dir)
        native_libs = [lib for lib in rv.libraries
                       if lib.matches(features) and lib.is_native()]
        # Only overwrite generated native files; preserve other existing directory contents.
        natives_dir.mkdir(parents=True, exist_ok=True)
        pairs = []
        for lib in native_libs:
            path, _source = self.resolve_library_file(lib)
            if path is not None:
                pairs.append((lib, path))
        extract_all_natives_from(pairs, natives_dir)
        return natives_dir

    def create_instance(self, base_id: str, name: str) -> str:
        """Create an isolated instance without copying or editing its parent's data."""
        self.resolver.resolve(base_id)
        target = self.assert_writable(self.version_dir(name))
        target.mkdir(parents=True, exist_ok=False)
        write_text(target / f"{name}.json", json.dumps(
            {"id": name, "inheritsFrom": base_id, "type": "release"}, ensure_ascii=False, indent=2))
        (target / ".isolate").write_text("1", encoding="utf-8")
        return name

    def clone_instance(self, source_id: str, name: str, cancel=None, progress=None) -> str:
        """Copy one instance into a new isolated directory without changing its source."""
        import stat
        import tempfile

        source = self.version_dir(source_id)
        target = self.assert_writable(self.version_dir(name))
        self.assert_idle(source_id)
        self.resolver.resolve(source_id)
        if target.exists():
            raise FileExistsError(f"实例已存在：{name}")
        run = self.run_dir(source_id)
        shared = run.resolve() != source.resolve()
        if shared:
            for other in self.list_installed():
                if other != source_id and self.run_dir(other).resolve() == run.resolve():
                    self.assert_idle(other)
        shared_names = ('mods', 'config', 'saves', 'resourcepacks', 'shaderpacks',
                        'screenshots', 'schematics', 'options.txt', 'servers.dat',
                        'servers.dat_old', 'optionsof.txt', 'optionsshaders.txt')

        def copy_safe(src, dst):
            if cancel is not None and cancel.is_set():
                raise RuntimeError('复制已取消')
            info = src.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                raise ValueError(f'实例包含无法安全复制的链接：{src}')
            if src.is_dir():
                dst.mkdir()
                for item in src.iterdir():
                    if item.name not in ('.instance.lock', '.craftbridge-trash', '.craftbridge-backups'):
                        copy_safe(item, dst / item.name)
            elif src.is_file():
                shutil.copy2(src, dst)
            else:
                raise ValueError(f'无法复制特殊文件：{src}')

        with tempfile.TemporaryDirectory(prefix='.onion-clone-', dir=self.versions_dir) as tmp:
            staging = Path(tmp) / 'instance'
            staging.mkdir()
            for item in source.iterdir():
                if item.name in ('.instance.lock', '.craftbridge-trash', '.craftbridge-backups') or item.name.startswith('natives-'):
                    continue
                new_name = name + item.name[len(source_id):] if item.name in (source_id+'.json', source_id+'.jar') else item.name
                if progress: progress('正在复制 · ' + item.name)
                copy_safe(item, staging / new_name)
            if shared:
                for entry in shared_names:
                    src, dst = run / entry, staging / entry
                    if src.exists() and not dst.exists():
                        if progress: progress('正在复制 · ' + entry)
                        copy_safe(src, dst)
            manifest = staging / (name + '.json')
            raw = json.loads(manifest.read_text(encoding='utf-8-sig'))
            raw['id'] = name
            if raw.get('jar') == source_id and (staging / (name + '.jar')).is_file():
                raw['jar'] = name
            manifest.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
            (staging / '.isolate').write_text('1', encoding='utf-8')
            if cancel is not None and cancel.is_set():
                raise RuntimeError('复制已取消')
            # Windows rename refuses an existing destination; never overwrite an instance.
            staging.rename(target)
        return name

    # ------------------------------------------------------------------ 校验/删除

    def verify(self, version_id: str, features: Optional[dict] = None,
               deep: bool = False) -> list[str]:
        """检查安装完整性，返回问题列表（空列表表示完整）。

        deep=True 时额外做 SHA-1 校验（客户端 jar 与依赖库），可检出损坏文件。
        """
        problems: list[str] = []
        try:
            rv = self.resolver.resolve(version_id, features)
        except VersionNotFound:
            return [f"缺少版本 JSON：{version_id}"]
        jar = self.client_jar_path(rv)
        if not jar.exists():
            problems.append(f"缺少客户端 jar：{jar.name}")
        elif deep:
            want = (rv.client or {}).get("sha1")
            if want and jar.parent.name == (rv.client_version_id or rv.id) and sha1_of(jar) != want:
                problems.append(f"客户端 jar 损坏：{jar.name}")
        for lib in rv.libraries:
            if not lib.matches(features):
                continue
            p, origin = self.resolve_library_file(lib)
            if p is None:
                problems.append(f"缺少依赖库：{lib.name}")
                continue
            if deep and origin == "workspace":
                sha1 = ((lib.native_download() or {}).get("sha1") if lib.is_native()
                        else lib.artifact_info()[0])
                if sha1 and sha1_of(p) != sha1:
                    problems.append(f"依赖库损坏：{lib.name}")
        if rv.asset_index:
            index_path = child(self.assets_dir / "indexes", f"{rv.asset_index_id}.json")
            objects_dir = self.assets_dir / "objects"
            reference = self.reference_assets_dir()
            if not index_path.is_file() and reference is not None:
                index_path = child(reference / "indexes", f"{rv.asset_index_id}.json")
                objects_dir = reference / "objects"
            try:
                index = AssetIndex.parse(json.loads(index_path.read_text(encoding="utf-8")), rv.asset_index_id)
                missing = index.missing_count(objects_dir)
                if missing:
                    problems.append(f"缺少或大小不符的资源对象：{missing} 个")
            except (OSError, ValueError, KeyError) as exc:
                problems.append(f"资源索引不可用：{rv.asset_index_id}（{exc}）")
        return problems

    def download_jobs(self, jobs, on_progress=None) -> None:
        for job in jobs:
            self.assert_writable(job.path)
        _ok, failed = self.downloader.download_many(jobs, on_progress=on_progress)
        if failed:
            raise DownloadError(f"下载未完成（{len(failed)} 个文件）：{failed[0]}；{getattr(failed[0], 'error', '')}")

    def delete_version(self, version_id: str) -> Path | None:
        self.invalidate_library_cache()
        """删除版本目录（含隔离目录）。"""
        target = self.assert_writable(self.version_dir(version_id))
        self.assert_idle(version_id)
        for other in self.list_installed():
            if other != version_id and self.resolver.load_raw(other).get("inheritsFrom") == version_id:
                raise RuntimeError(f"实例 {other} 依赖此版本，请先处理依赖实例")
        if target.exists():
            return recycle(target, self.versions_dir)

    def import_external_version(self, source_versions_dir, version_id: str) -> str:
        """把外部 .minecraft 的某个版本（json + jar）拷贝进工作区，返回版本 id。

        只做只读拷贝，不改动源目录；库与资源由后续 install() 补齐。
        """
        src_dir = Path(source_versions_dir)
        if src_dir.resolve() == self.versions_dir.resolve():
            return version_id
        src_json = src_dir / version_id / f"{version_id}.json"
        if not src_json.exists():
            raise VersionNotFound(f"外部版本不存在：{version_id}")
        dest_dir = self.version_dir(version_id)
        if dest_dir.exists():
            return version_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_json, dest_dir / f"{version_id}.json")
        src_jar = src_dir / version_id / f"{version_id}.jar"
        if src_jar.exists():
            shutil.copy2(src_jar, dest_dir / f"{version_id}.jar")
        return version_id
