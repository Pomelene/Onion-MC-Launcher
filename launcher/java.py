# -*- coding: utf-8 -*-
"""Java 运行时：发现、版本识别与自动下载。

- 发现：JAVA_HOME、PATH、常见安装目录、启动器自带的 runtime/
- 识别：执行 java -version 解析大版本号
- 下载：Mojang 官方 Java 运行时清单（按游戏所需大版本选择组件）
"""

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .download import DownloadJob, Downloader
from .paths import COMMON_JAVA_ROOTS, app_root

#: Mojang Java 运行时清单（全平台）
JAVA_RUNTIME_MANIFEST = (
    "https://piston-meta.mojang.com/v1/products/java-runtime/"
    "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"
)

#: 大版本 -> Mojang 运行时组件名（HMCL GameJavaVersion 的映射）
JAVA_COMPONENTS = {8: "jre-legacy", 16: "java-runtime-alpha", 17: "java-runtime-beta",
                   21: "java-runtime-delta", 25: "java-runtime-epsilon"}

_VERSION_RE = re.compile(r'version "(\d+)(?:\.(\d+))?' + chr(39))


@dataclass
class JavaInfo:
    """一个可用的 Java 运行时。"""

    path: Path
    major: int
    version: str = ""

    @property
    def executable(self) -> str:
        return str(self.path)


def _java_binary_in(java_home: Path) -> Optional[Path]:
    name = "java.exe" if os.name == "nt" else "java"
    candidate = java_home / "bin" / name
    return candidate if candidate.is_file() else None


def probe_java(path: Path) -> Optional[JavaInfo]:
    """执行 java -version 并解析大版本号；失败返回 None。"""
    try:
        proc = subprocess.run([str(path), "-version"], capture_output=True,
                              timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")
    m = re.search(r'version "(\d+)(?:\.(\d+))?[^"]*"', text)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):  # 1.8.0_392 这类旧写法
        major = int(m.group(2))
    version = m.group(0).split('"')[1] if '"' in m.group(0) else ""
    return JavaInfo(path=path, major=major, version=version)


def _candidate_paths() -> list[Path]:
    """收集可能存在的 java 可执行文件。"""
    result: list[Path] = []
    env_home = os.environ.get("JAVA_HOME")
    if env_home:
        p = _java_binary_in(Path(env_home))
        if p:
            result.append(p)
    which = shutil.which("java")
    if which:
        result.append(Path(which))
    for root in COMMON_JAVA_ROOTS:
        base = Path(root)
        if not base.exists():
            continue
        # 兼容 "C:\\Program Files\\Java\\jdk-17\\bin\\java.exe" 这类布局
        direct = _java_binary_in(base)
        if direct:
            result.append(direct)
            continue
        for sub in base.iterdir():
            if sub.is_dir():
                p = _java_binary_in(sub)
                if p:
                    result.append(p)
    # 启动器自带的运行时目录
    runtime_root = app_root() / "runtime"
    if runtime_root.exists():
        for sub in runtime_root.iterdir():
            if sub.is_dir():
                p = _java_binary_in(sub)
                if p:
                    result.append(p)
    return result


def find_all_java() -> list[JavaInfo]:
    """探测所有可用 Java，按大版本去重（保留首个）。"""
    seen: set[str] = set()
    result: list[JavaInfo] = []
    for path in _candidate_paths():
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        info = probe_java(path)
        if info:
            result.append(info)
    return result


def pick_java(required: Optional[int], explicit: str = "") -> Optional[JavaInfo]:
    """选择 Java：显式指定优先；否则挑大版本最贴近要求的那个。"""
    if explicit:
        info = probe_java(Path(explicit))
        if info:
            return info
    candidates = find_all_java()
    if not candidates:
        return None
    if required is None:
        return max(candidates, key=lambda j: j.major)
    exact = [j for j in candidates if j.major == required]
    if exact:
        return exact[0]
    newer = sorted((j for j in candidates if j.major > required), key=lambda j: j.major)
    if newer:
        return newer[0]
    return max(candidates, key=lambda j: j.major)


def resolve_java(required, explicit: str, downloader,
                 on_stage=None, on_progress=None):
    """确定用于启动的 Java。

    策略：显式指定 > 本机精确大版本命中 > 自动下载精确大版本；
    找不到精确版本时返回 None（由调用方报错），不再回退到较新/任意版本，
    避免 Java 大版本不兼容导致游戏无法启动。
    """
    if explicit:
        info = probe_java(Path(explicit))
        if info:
            return info
    candidates = find_all_java()
    if required is None:
        # 版本未声明 Java 需求时，取本机最高版本
        return max(candidates, key=lambda x: x.major) if candidates else None
    exact = next((c for c in candidates if c.major == required), None)
    if exact:
        return exact
    downloaded = download_java(required, downloader, on_stage, on_progress)
    if downloaded:
        return downloaded
    return None


def runtime_dir(component: str) -> Path:
    return app_root() / "runtime" / component


def download_java(major: int, downloader: Downloader,
                  on_stage=None, on_progress=None) -> Optional[JavaInfo]:
    """下载 Mojang 官方 Java 运行时到 runtime/ 下，返回可用的 JavaInfo。"""
    component = JAVA_COMPONENTS.get(major)
    if not component:
        return None
    if on_stage:
        on_stage(f"获取 Java {major} 运行时清单")
    data = downloader.fetch_json(JAVA_RUNTIME_MANIFEST)
    platform_key = _platform_key()
    entries = (data.get(platform_key) or {}).get(component) or []
    if not entries:
        return None
    entry = entries[0]
    manifest_url = entry["manifest"]["url"]
    dest = runtime_dir(component)
    dest.mkdir(parents=True, exist_ok=True)
    if on_stage:
        on_stage(f"下载 Java {major} 运行时（{entry.get('version', {}).get('name', '')}）")
    manifest = downloader.fetch_json(manifest_url)
    files = manifest.get("files") or {}
    jobs: list[DownloadJob] = []
    for rel, meta in files.items():
        if meta.get("type") != "file":
            continue
        raw = (meta.get("downloads") or {}).get("raw")
        if not raw:
            continue
        target = dest / rel
        jobs.append(DownloadJob(raw["url"], target, sha1=raw.get("sha1"),
                                size=raw.get("size"), name=rel))
    if on_progress:
        on_progress(0, len(jobs))
    ok, failed = downloader.download_many(
        jobs,
        on_progress=lambda done, total: on_progress(done, total) if on_progress else None,
    )
    if failed:
        return None
    exe = _java_binary_in(dest)
    return probe_java(exe) if exe else None


def list_downloadable(downloader: Downloader) -> list[dict]:
    """列出 Mojang 官方可下载的 Java 运行时（按大版本）。"""
    data = downloader.fetch_json(JAVA_RUNTIME_MANIFEST)
    platform_key = _platform_key()
    result = []
    for major, component in JAVA_COMPONENTS.items():
        entries = (data.get(platform_key) or {}).get(component) or []
        if not entries:
            continue
        ver = entries[0].get("version", {}) or {}
        result.append({
            "major": major,
            "component": component,
            "name": ver.get("name", component),
            "released": ver.get("released", ""),
        })
    return result


def _platform_key() -> str:
    """Mojang Java 清单的平台键。"""
    machine = platform.machine().lower()
    if os.name == "nt":
        return "windows-arm64" if "arm" in machine else ("windows-x86" if "32" in machine else "windows-x64")
    if platform.system() == "Darwin":
        return "mac-os-arm64" if "arm" in machine else "mac-os"
    return "linux-i386" if "32" in machine else "linux"
