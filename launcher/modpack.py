# -*- coding: utf-8 -*-
"""整合包导入：Modrinth .mrpack（完整支持）与 CurseForge 整合包（部分支持）。

导入时会创建一个独立版本（versions/<id>/.isolate 标记），
其 mods/、config/ 等资源只属于该整合包，不污染全局游戏目录。
"""

import hashlib
import copy
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .download import DownloadError, DownloadJob
from .archives import validate_archive,copy_member,read_member


@dataclass
class ModpackInfo:
    """整合包元信息。"""

    kind: str                 # mrpack | curseforge
    name: str
    version: str
    game_version: str
    loader: str = ""          # fabric | quilt | forge | neoforge
    loader_version: str = ""


def _read_json(zf: zipfile.ZipFile, name: str) -> Optional[dict]:
    try:
        return json.loads(read_member(zf,name).decode("utf-8", "replace"))
    except (KeyError, json.JSONDecodeError, OSError):
        return None


def read_modpack_info(path: Path) -> ModpackInfo:
    """识别整合包类型并读取基本信息。"""
    with zipfile.ZipFile(path) as zf:
        validate_archive(zf)
        index = _read_json(zf, "modrinth.index.json")
        if index is not None:
            deps = index.get("dependencies") or {}
            loader, loader_ver = "", ""
            for key in ("fabric-loader", "quilt-loader", "forge", "neoforge"):
                if key in deps:
                    loader = key.replace("-loader", "")
                    loader_ver = str(deps[key])
                    break
            return ModpackInfo(
                kind="mrpack",
                name=str(index.get("name") or path.stem),
                version=str(index.get("versionId") or "1.0"),
                game_version=str(deps.get("minecraft") or ""),
                loader=loader,
                loader_version=loader_ver,
            )
        manifest = _read_json(zf, "manifest.json")
        if manifest is not None and "minecraft" in manifest:
            mc = manifest.get("minecraft") or {}
            loaders = mc.get("modLoaders") or []
            primary = next((m for m in loaders if m.get("primary")), loaders[0] if loaders else {})
            loader_id = str(primary.get("id", ""))
            kind = re.split(r"[-_]", loader_id)[0] if loader_id else ""
            version = loader_id.split("-", 1)[1] if "-" in loader_id else ""
            return ModpackInfo(
                kind="curseforge",
                name=str(manifest.get("name") or path.stem),
                version=str(manifest.get("version") or "1.0"),
                game_version=str(mc.get("version") or ""),
                loader=kind,
                loader_version=version,
            )
    raise DownloadError("无法识别的整合包格式（需要 modrinth.index.json 或 manifest.json）")


def _safe_extract(zf: zipfile.ZipFile, folder: str, target: Path, cancel_event=None) -> int:
    """把 zip 中 folder/ 前缀的内容解压到 target，防路径穿越。"""
    validate_archive(zf)
    count = 0
    for info in zf.infolist():
        if info.filename.endswith("/") or not info.filename.startswith(folder + "/"):
            continue
        rel = info.filename[len(folder) + 1:]
        from .safety import child
        try:
            dest = child(target, rel)
        except (ValueError, PermissionError):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        copy_member(zf,info,dest,cancel_event=cancel_event)
        count += 1
    return count


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", text or "modpack")
    return cleaned.strip("-")[:40] or "modpack"


def _standalone_profile(repo, version_id, game_version):
    """Flatten raw inheritance while retaining conditional arguments and libraries."""
    chain=[];seen=set();current=version_id
    while current:
        if current in seen:raise DownloadError('整合包版本继承存在循环')
        seen.add(current);data=repo.resolver.load_raw(current);chain.append(data);current=data.get('inheritsFrom')
    merged={}
    for data in reversed(chain):merged.update(copy.deepcopy(data))
    merged['libraries']=[copy.deepcopy(lib) for data in chain for lib in data.get('libraries',[])]
    arguments={}
    for data in reversed(chain):
        for kind,values in (data.get('arguments') or {}).items():arguments.setdefault(kind,[]).extend(copy.deepcopy(values))
    if arguments:merged['arguments']=arguments
    merged.pop('inheritsFrom',None);merged.pop('jar',None)
    merged['id']=version_id;merged['onionGameVersion']=game_version
    resolved=repo.resolver.resolve(version_id);source=repo.client_jar_path(resolved)
    merged['mainClass']=resolved.main_class
    if resolved.asset_index:merged['assetIndex']=copy.deepcopy(resolved.asset_index)
    if resolved.java_major is not None:
        merged['javaVersion']={**(merged.get('javaVersion') or {}),'majorVersion':resolved.java_major}
    if resolved.logging:merged['logging']={'client':copy.deepcopy(resolved.logging)}
    downloads=merged.get('downloads') or {}
    if resolved.client:downloads['client']=copy.deepcopy(resolved.client)
    merged['downloads']=downloads
    if not source.is_file():raise DownloadError('整合包客户端文件尚未准备完成')
    destination=repo.version_dir(version_id)/f'{version_id}.jar'
    if source!=destination:shutil.copy2(source,destination)
    if resolved.jar_id and resolved.jar_id!=resolved.client_version_id:
        # A patched loader jar is not interchangeable with Mojang's vanilla jar.
        merged.setdefault('downloads',{}).pop('client',None)
    return merged


def import_modpack(repo, archive: Path, on_stage=None, on_progress=None) -> str:
    """Publish exactly one self-contained instance after the whole import succeeds."""
    from .repository import GameRepository
    from .version import VersionResolver
    from .safety import child
    info=read_modpack_info(archive)
    base=f'{_slug(info.name)}-{info.game_version}';pack_id=base;suffix=2
    while repo.version_dir(pack_id).exists():pack_id=f'{base}-{suffix}';suffix+=1
    target=repo.assert_writable(repo.version_dir(pack_id))
    cache=child(repo.game_dir,'.onion/install');cache.mkdir(parents=True,exist_ok=True)
    from .storage import _hide
    _hide(cache.parent)
    with tempfile.TemporaryDirectory(dir=cache,prefix='pack-',ignore_cleanup_errors=True) as temporary:
        config=copy.copy(repo.config);config.data=dict(repo.config.data);config.data['game_dir']=str(repo.game_dir)
        staged=GameRepository(config);staged.versions_dir=Path(temporary)/'versions';staged.resolver=VersionResolver(staged.versions_dir)
        # Reuse only runtime metadata/client jars, never copy another instance's
        # mods, saves or configuration into the new pack.
        seeds=[info.game_version]
        if info.loader in ('fabric','quilt') and info.loader_version:
            seeds.append(f'{info.loader}-loader-{info.loader_version}-{info.game_version}')
        seen=set()
        while seeds:
            ident=seeds.pop()
            if ident in seen:continue
            seen.add(ident);original=repo.resolver.json_path(ident)
            if not original.is_file():continue
            data=repo.resolver.load_raw(ident);folder=staged.version_dir(ident);folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{ident}.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            jar=original.with_suffix('.jar')
            if jar.is_file():shutil.copy2(jar,folder/jar.name)
            if data.get('inheritsFrom'):seeds.append(data['inheritsFrom'])
        cancel=repo.downloader._cancel_event()
        telemetry=getattr(repo.downloader._local,'on_bytes',None)
        with staged.downloader.cancellable(cancel,telemetry):
            _import_modpack(staged,archive,on_stage,on_progress,pack_id)
        if cancel is not None and cancel.is_set():raise DownloadError('整合包导入已取消')
        profile=_standalone_profile(staged,pack_id,info.game_version)
        source=staged.version_dir(pack_id)
        (source/f'{pack_id}.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
        if cancel is not None and cancel.is_set():raise DownloadError('整合包导入已取消')
        repo.versions_dir.mkdir(parents=True,exist_ok=True)
        if target.exists():raise FileExistsError('整合包目标目录已存在，请重试')
        source.rename(target)
    repo.invalidate_library_cache()
    if on_stage:on_stage(f'整合包导入完成：{pack_id}')
    return pack_id


def _import_modpack(repo, archive: Path, on_stage=None, on_progress=None, target_id=None) -> str:
    """导入整合包，返回新版本 id。"""
    def stage(text: str) -> None:
        if on_stage:
            on_stage(text)

    info = read_modpack_info(archive)
    stage(f"读取整合包：{info.name} {info.version}")
    if not info.game_version:
        raise DownloadError("整合包未声明 Minecraft 版本")
    supported = {"fabric", "quilt", "forge", "neoforge"}
    if info.loader and info.loader not in supported:
        raise DownloadError(f"暂不支持该整合包的加载器：{info.loader}")

    stage("安装原版游戏")
    repo.install(info.game_version, on_stage, on_progress)

    loader_version_id = info.game_version
    if info.loader in ("fabric", "quilt"):
        from .install.fabric import install_loader
        stage(f"安装 {info.loader} 加载器")
        loader_version_id = install_loader(
            repo, info.game_version, info.loader_version or None, info.loader, stage)
        repo.install(loader_version_id, on_stage, on_progress)
    elif info.loader in ("forge", "neoforge"):
        from .install.forge import install_forge
        stage(f"安装 {info.loader} 加载器")
        loader_version_id = install_forge(
            repo, info.game_version, info.loader, info.loader_version, stage, on_progress)
        repo.install(loader_version_id, on_stage, on_progress)

    base_pack = f"{_slug(info.name)}-{info.game_version}"
    pack_id = target_id or base_pack
    suffix = 2
    while repo.version_dir(pack_id).exists():
        pack_id = f"{base_pack}-{suffix}"
        suffix += 1
    instance = repo.version_dir(pack_id)
    instance.mkdir(parents=True, exist_ok=True)
    (instance / ".isolate").write_text("1", encoding="utf-8")

    manifest = {"id": pack_id, "inheritsFrom": loader_version_id, "type": "release"}
    (instance / f"{pack_id}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    files_installed = 0
    with zipfile.ZipFile(archive) as zf:
        validate_archive(zf)
        cancel_event=getattr(repo.downloader,'_cancel_event',lambda:None)()
        index = _read_json(zf, "modrinth.index.json")
        if index is not None:
            stage("下载整合包模组文件")
            jobs = []
            for entry in index.get("files") or []:
                env = entry.get("env") or {}
                if str(env.get("client", "required")).lower() == "unsupported":
                    continue
                rel = entry.get("path") or ""
                downloads = entry.get("downloads") or []
                if not rel or not downloads:
                    continue
                from .safety import child
                target = child(instance, rel)
                hashes = entry.get("hashes") or {}
                jobs.append(DownloadJob(downloads[0], target,
                                        sha1=hashes.get("sha1"),
                                        size=entry.get("fileSize"), name=Path(rel).name,
                                        fallback_urls=tuple(downloads[1:])))
            if jobs:
                repo.download_jobs(jobs, on_progress)
            files_installed += len(jobs)
            stage("解压整合包覆盖文件")
            _safe_extract(zf, "overrides", instance,cancel_event)
            _safe_extract(zf, "client-overrides", instance,cancel_event)
        else:
            stage("解压整合包覆盖文件")
            _safe_extract(zf, "overrides", instance,cancel_event)
            manifest_data = _read_json(zf, "manifest.json") or {}
            entries = manifest_data.get("files") or []
            if entries:
                stage(f"解析 CurseForge 文件（{len(entries)} 个）")
                files_installed += _install_curseforge_files(
                    repo, instance, entries, on_stage, on_progress)

    stage(f"整合包文件已就绪：{pack_id}")
    return pack_id


def _install_curseforge_files(repo, instance: Path, entries: list[dict],
                              on_stage=None, on_progress=None) -> int:
    """按 CurseForge manifest 的文件清单解析元数据并下载。"""
    from .curseforge import CurseForgeClient

    client = CurseForgeClient(repo.downloader,
                              repo.config.get("curseforge_api_key") or "")
    jobs: list[DownloadJob] = []
    problems: list[str] = []
    optional_skipped = 0
    for entry in entries:
        required = bool(entry.get("required", True))
        project_id = entry.get("projectID")
        file_id = entry.get("fileID")
        if not project_id or not file_id:
            continue
        try:
            meta = client.file(int(project_id), int(file_id))
            url = client.file_url(meta)
        except Exception as exc:  # noqa: BLE001
            if required:
                problems.append(f"{project_id}/{file_id}: {exc}")
            else:
                optional_skipped += 1
            continue
        name = str(meta.get("fileName") or f"{project_id}-{file_id}.jar")
        folder = client.target_dir(meta)
        sha1 = ""
        hashes = meta.get("hashes") or {}
        if isinstance(hashes, dict):
            sha1 = str(hashes.get("sha1") or "")
        elif isinstance(hashes, list):
            for item in hashes:
                if str(item.get("algo")) in ("1", "sha1"):
                    sha1 = str(item.get("value") or "")
                    break
        from .safety import child
        jobs.append(DownloadJob(url, child(instance, str(Path(folder) / name)),
                                sha1=sha1 if len(sha1) == 40 else None,
                                size=meta.get("fileLength"), name=name))
    if problems:
        raise DownloadError("CurseForge 文件解析失败：" + "；".join(problems[:3]))
    if optional_skipped and on_stage:
        on_stage(f"跳过 {optional_skipped} 个无法解析的可选文件")
    if jobs:
        _ok, failed = repo.downloader.download_many(jobs, on_progress=on_progress)
        if failed:
            raise DownloadError(f"CurseForge 文件下载失败（{len(failed)} 个）：{failed[0]}")
    return len(jobs)


# ---------------------------------------------------------------- 导出

def _base_version(repo, version_id: str) -> str:
    """沿 inheritsFrom 链找到最底层的原版版本号。"""
    vid = version_id
    try:
        data = repo.resolver.load_raw(vid)
        if data.get('onionGameVersion'):return str(data['onionGameVersion'])
        seen = {vid}
        while data.get("inheritsFrom"):
            vid = data["inheritsFrom"]
            if vid in seen:
                raise ValueError("版本继承存在循环")
            seen.add(vid)
            data = repo.resolver.load_raw(vid)
    except Exception:  # noqa: BLE001
        return version_id
    return vid


def _detect_loader(repo, version_id: str) -> tuple[str, str]:
    """Prefer actual library coordinates, including inherited profiles."""
    try:
        for lib in repo.resolver.resolve(version_id).libraries:
            parts = lib.name.split(":")
            if len(parts) < 3:
                continue
            group, artifact, version = parts[:3]
            if group == "net.fabricmc" and artifact == "fabric-loader":
                return "fabric", version
            if group == "org.quiltmc" and artifact == "quilt-loader":
                return "quilt", version
            if group == "net.neoforged" and artifact in ("neoforge", "forge"):
                return "neoforge", version
            if group == "net.minecraftforge" and artifact in ("forge", "fmlloader"):
                base = _base_version(repo, version_id)
                return "forge", version.removeprefix(base + "-")
    except (OSError, ValueError):
        pass
    vid = version_id.lower()
    for name in ("fabric", "quilt", "neoforge", "forge"):
        if name in vid:
            return name, ""
    return "", ""


def _sha512(path: Path) -> str:
    try:
        h = hashlib.sha512()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _sha1(path: Path) -> str:
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def export_mrpack(repo, version_id: str, out_path: Path, name: str = "") -> Path:
    """把某个版本的 mods / config 等打包为 .mrpack，返回输出路径。

    为兼容外部工具，mods 同时写入 overrides/mods（保证可导入）并列出哈希；
    本启动器导入时若 overrides 中已有文件则无需联网下载。
    """
    base = _base_version(repo, version_id)
    loader, loader_ver = _detect_loader(repo, version_id)
    run_dir = repo.run_dir(version_id)
    mods_dir = run_dir / "mods"

    files = []
    if mods_dir.is_dir():
        for p in sorted(mods_dir.glob("*.jar")) + sorted(mods_dir.glob("*.zip")):
            try:
                size = p.stat().st_size
            except OSError:
                continue
            files.append({
                "path": f"mods/{p.name}",
                "hashes": {"sha1": _sha1(p), "sha512": _sha512(p)},
                "env": {"client": "required", "server": "required"},
                "downloads": [],
                "fileSize": size,
            })

    deps = {"minecraft": base}
    if loader:
        deps[f"{loader}-loader" if loader in ("fabric", "quilt") else loader] = loader_ver

    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "1.0",
        "name": name or version_id,
        "summary": "由 Onion Minecraft Launcher 导出",
        "files": files,
        "dependencies": deps,
    }

    override_dirs = ("config", "resourcepacks", "shaderpacks", "kubejs",
                     "scripts", "options.txt", "servers.dat", "optionsof.txt",
                     "optionsshaders.txt")
    out_path = Path(out_path)
    if out_path.resolve().is_relative_to(run_dir.resolve()):
        raise ValueError("请将整合包导出到实例目录之外")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import uuid
    temporary = out_path.with_name(out_path.name + "." + uuid.uuid4().hex + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modrinth.index.json", json.dumps(index, ensure_ascii=False))
        for sub in override_dirs:
            p = run_dir / sub
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"overrides/{f.relative_to(run_dir)}")
            elif p.is_file():
                zf.write(p, f"overrides/{sub}")
        # 模组同步写入 overrides，保证离线可导入
        if mods_dir.is_dir():
            for p in sorted(mods_dir.glob("*.jar")) + sorted(mods_dir.glob("*.zip")):
                zf.write(p, f"overrides/mods/{p.name}")
    from .safety import backup_file
    backup_file(out_path)
    temporary.replace(out_path)
    return out_path
