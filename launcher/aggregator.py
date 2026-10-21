# -*- coding: utf-8 -*-
"""多源信息聚合：并行拉取、逐源状态、磁盘缓存（仿 HMCL 的同步显示）。

设计要点：
- 每个源独立超时与重试，一个源失败不影响其它源；
- 先返回磁盘缓存（即使过期），再后台刷新，界面不会白屏；
- 状态逐源回调，UI 可以显示“加载中 → 成功/失败”的实时变化；
- 所有网络调用都在工作线程，Tk 主线程不阻塞。
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .java import JAVA_COMPONENTS
from .paths import app_root

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
BMCLAPI_MANIFEST = "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"
FABRIC_LOADER = "https://meta.fabricmc.net/v2/versions/loader"
QUILT_LOADER = "https://meta.quiltmc.org/v3/versions/loader"
FORGE_META = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
FORGE_META_MIRROR = "https://bmclapi2.bangbang93.com/maven/net/minecraftforge/forge/maven-metadata.xml"
NEOFORGE_META = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
JAVA_RUNTIME = "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
MODRINTH_TAGS = "https://api.modrinth.com/v2/tag/game_version"

#: key -> (显示名, 缓存有效期秒)
SOURCES: dict[str, tuple[str, int]] = {
    "mojang": ("Mojang 官方", 1800),
    "bmclapi": ("BMCLAPI 镜像", 1800),
    "fabric": ("Fabric", 21600),
    "quilt": ("Quilt", 21600),
    "forge": ("Forge", 21600),
    "neoforge": ("NeoForge", 21600),
    "java": ("Java 运行时", 86400),
    "modrinth": ("Modrinth 标签", 86400),
}


@dataclass
class SourceStatus:
    """一个源的状态。"""

    key: str
    name: str
    state: str = "idle"          # idle | loading | ok | fail
    count: int = 0
    latency_ms: int = 0
    error: str = ""
    fetched_at: float = 0.0
    from_cache: bool = False

    @property
    def stale(self) -> bool:
        ttl = SOURCES.get(self.key, ("", 0))[1]
        return bool(self.fetched_at) and (time.time() - self.fetched_at) > ttl

    def label(self) -> str:
        if self.state == "loading":
            return f"{self.name} · 加载中"
        if self.state == "fail":
            return f"{self.name} · 失败"
        if self.state == "ok":
            mark = "缓存" if self.from_cache else f"{self.latency_ms}ms"
            return f"{self.name} · {self.count} 项 · {mark}"
        return f"{self.name} · 未加载"


def _parse_versions(data: dict) -> list[dict]:
    items = []
    for v in data.get("versions") or []:
        items.append({"id": v.get("id"), "type": v.get("type"),
                      "releaseTime": v.get("releaseTime") or v.get("time", "")})
    return items


def _parse_xml_versions(text: str) -> list[str]:
    return re.findall(r"<version>([^<]+)</version>", text or "")


def _loader_list(data) -> list[dict]:
    out = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        loader = item.get("loader") if isinstance(item.get("loader"), dict) else item
        version = loader.get("version") or item.get("version")
        if not version:
            continue
        out.append({"version": str(version), "stable": bool(
            loader.get("stable", item.get("stable", True)))})
    return out


class InfoHub:
    """多源信息中心。"""

    def __init__(self, downloader, cache_dir: Optional[Path] = None,
                 timeout: float = 12.0) -> None:
        self.downloader = downloader
        self.cache_dir = Path(cache_dir or (app_root() / "config" / "cache"))
        self.timeout = timeout
        self.data: dict[str, object] = {}
        self.statuses: dict[str, SourceStatus] = {
            key: SourceStatus(key=key, name=name) for key, (name, _ttl) in SOURCES.items()}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------ 缓存

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def load_cache(self) -> None:
        """载入磁盘缓存（无论是否过期，先让界面有内容）。"""
        for key in SOURCES:
            path = self._cache_path(key)
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload = raw.get("data")
            if payload is None:
                continue
            with self._lock:
                self.data[key] = payload
                status = self.statuses[key]
                status.state = "ok"
                status.count = len(payload) if isinstance(payload, list) else 1
                status.fetched_at = float(raw.get("fetched_at") or 0)
                status.from_cache = True

    def _save_cache(self, key: str, payload) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(key)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fetched_at": time.time(), "data": payload},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    # ------------------------------------------------------------ 拉取

    def _fetch(self, key: str):
        """抓取单个源，返回规范化后的数据。"""
        if key == "mojang":
            return _parse_versions(self.downloader.fetch_json(MOJANG_MANIFEST))
        if key == "bmclapi":
            return _parse_versions(self.downloader.fetch_json(BMCLAPI_MANIFEST))
        if key == "fabric":
            return _loader_list(self.downloader.fetch_json(FABRIC_LOADER))
        if key == "quilt":
            return _loader_list(self.downloader.fetch_json(QUILT_LOADER))
        if key == "forge":
            try:
                text = self.downloader.fetch(FORGE_META)
            except Exception:  # noqa: BLE001
                text = self.downloader.fetch(FORGE_META_MIRROR)
            return _parse_xml_versions(text)
        if key == "neoforge":
            return _parse_xml_versions(self.downloader.fetch(NEOFORGE_META))
        if key == "java":
            data = self.downloader.fetch_json(JAVA_RUNTIME)
            name_to_major = {v: k for k, v in JAVA_COMPONENTS.items()}
            majors = set()
            for _platform, components in (data or {}).items():
                if not isinstance(components, dict):
                    continue
                for name in components:
                    if name in name_to_major:
                        majors.add(name_to_major[name])
            return sorted(majors)
        if key == "modrinth":
            return self.downloader.fetch_json(MODRINTH_TAGS)
        raise ValueError(f"未知源：{key}")

    def _notify(self, on_status, status: SourceStatus) -> None:
        if on_status is None:
            return
        try:
            on_status(status)
        except Exception:  # noqa: BLE001
            pass

    def refresh(self, keys: Optional[list[str]] = None, force: bool = False,
                on_status: Optional[Callable[[SourceStatus], None]] = None) -> None:
        """并行刷新指定源（阻塞直到全部落定）。"""
        targets = [k for k in (keys or list(SOURCES)) if k in SOURCES]
        if not force:
            targets = [k for k in targets if not (
                self.statuses[k].state == "ok" and not self.statuses[k].stale)]
        if not targets:
            return
        for key in targets:
            with self._lock:
                self.statuses[key].state = "loading"
            self._notify(on_status, self.statuses[key])

        def work(key: str):
            started = time.time()
            try:
                payload = self._fetch(key)
                return key, payload, int((time.time() - started) * 1000), ""
            except Exception as exc:  # noqa: BLE001
                return key, None, int((time.time() - started) * 1000), str(exc)[:160]

        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
            futures = [pool.submit(work, key) for key in targets]
            for future in as_completed(futures):
                key, payload, latency, error = future.result()
                with self._lock:
                    status = self.statuses[key]
                    status.latency_ms = latency
                    if error:
                        status.state = "fail"
                        status.error = error
                    else:
                        status.state = "ok"
                        status.error = ""
                        status.from_cache = False
                        status.fetched_at = time.time()
                        status.count = len(payload) if isinstance(payload, list) else 1
                        self.data[key] = payload
                if not error:
                    self._save_cache(key, payload)
                self._notify(on_status, self.statuses[key])

    def refresh_async(self, keys: Optional[list[str]] = None, force: bool = False,
                      on_status=None) -> threading.Thread:
        """后台刷新（供 UI 使用，不阻塞主线程）。"""
        thread = threading.Thread(target=self.refresh,
                                  args=(keys, force, on_status), daemon=True)
        thread.start()
        self._thread = thread
        return thread

    # ------------------------------------------------------------ 查询

    def game_versions(self) -> list[dict]:
        """合并 Mojang 与镜像的版本清单，按 id 去重（官方优先）。"""
        merged: dict[str, dict] = {}
        for key in ("bmclapi", "mojang"):
            for item in self.data.get(key) or []:
                vid = item.get("id")
                if vid:
                    merged[vid] = dict(item)
        items = list(merged.values())
        items.sort(key=lambda v: v.get("releaseTime") or "", reverse=True)
        return items

    def loaders(self, key: str) -> list[dict]:
        raw = self.data.get(key) or []
        if key in ("fabric", "quilt"):
            return list(raw)
        out = []
        for version in raw:
            text = str(version)
            if key == "neoforge":
                out.append({"version": text, "stable": True})
            else:
                out.append({"version": text, "stable": True})
        return out

    def loaders_for_game(self, key: str, game_version: str) -> list[dict]:
        """按游戏版本过滤加载器版本（Forge/NeoForge 的版本号内嵌 MC 版本）。"""
        items = self.loaders(key)
        if not game_version:
            return items
        prefix = str(game_version)
        picked = []
        for item in items:
            version = str(item["version"])
            if key == "forge" and version.startswith(prefix + "-"):
                picked.append({"version": version[len(prefix) + 1:], "stable": True,
                               "full": version})
            elif key == "neoforge" and version.startswith(prefix + "."):
                picked.append({"version": version, "stable": True})
        return picked

    def status_list(self) -> list[SourceStatus]:
        return [self.statuses[key] for key in SOURCES]
