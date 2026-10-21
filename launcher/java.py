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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
    architecture: str = ""
    bits: int = 0

    @property
    def executable(self) -> str:
        return str(self.path)


def _java_binary_in(java_home: Path) -> Optional[Path]:
    name = "java.exe" if os.name == "nt" else "java"
    candidate = java_home / "bin" / name
    return candidate if candidate.is_file() else None


_PROBE_CACHE = {}
_PROBE_LOCK = threading.Lock()


def probe_java(path: Path, *, refresh=False) -> Optional[JavaInfo]:
    """Identify a runnable JVM from its actual properties, with bounded probing."""
    path=Path(path)
    if path.is_dir():path=_java_binary_in(path)
    if path is None:return None
    if path.name.lower()=='javaw.exe' and path.with_name('java.exe').is_file():path=path.with_name('java.exe')
    try:
        path=path.resolve();stamp=path.stat();key=(os.path.normcase(str(path)),stamp.st_size,stamp.st_mtime_ns)
    except (OSError,ValueError):return None
    with _PROBE_LOCK:
        cached=_PROBE_CACHE.get(key)
        if not refresh and cached and time.monotonic()-cached[0]<60:return cached[1]
    try:
        proc=subprocess.run([str(path),'-XshowSettings:properties','-version'],capture_output=True,timeout=5,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode:
            proc=subprocess.run([str(path),'-version'],capture_output=True,timeout=3,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode:return None
    except (OSError,subprocess.SubprocessError):return None
    text=((proc.stdout or b'')+b'\n'+(proc.stderr or b'')).decode('utf-8','replace')
    found=re.search(r'^\s*java\.version\s*=\s*(\S+)',text,re.M) or re.search(r'(?:openjdk|java)\s+(?:version\s+)?["\']?([0-9][0-9A-Za-z._+\-]*)',text,re.I)
    if not found:return None
    version=found.group(1);numbers=re.match(r'(\d+)(?:\.(\d+))?',version)
    if not numbers:return None
    major=int(numbers.group(2)) if numbers.group(1)=='1' and numbers.group(2) else int(numbers.group(1))
    arch_match=re.search(r'^\s*os\.arch\s*=\s*(\S+)',text,re.M)
    architecture=(arch_match.group(1).lower() if arch_match else '')
    bit_match=re.search(r'^\s*sun\.arch\.data\.model\s*=\s*(32|64)',text,re.M)
    bits=int(bit_match.group(1)) if bit_match else 64 if architecture in ('amd64','x86_64','aarch64','arm64') or '64-Bit' in text else 32 if architecture in ('x86','i386','i686') else 0
    info=JavaInfo(path,major,version,architecture,bits)
    with _PROBE_LOCK:
        if len(_PROBE_CACHE)>256:_PROBE_CACHE.clear()
        _PROBE_CACHE[key]=(time.monotonic(),info)
    return info


def _registry_homes():
    if os.name!='nt':return []
    try:import winreg
    except ImportError:return []
    homes=[]
    roots=[r'SOFTWARE\JavaSoft',r'SOFTWARE\Eclipse Adoptium',r'SOFTWARE\AdoptOpenJDK',r'SOFTWARE\Microsoft\JDK',r'SOFTWARE\Azul Systems\Zulu',r'SOFTWARE\BellSoft']
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            for root in roots:
                pending=[(root,0)];visited=0
                while pending and visited<256:
                    name,depth=pending.pop();visited+=1
                    try:
                        with winreg.OpenKey(hive,name,0,winreg.KEY_READ|view) as key:
                            for value_name in ('JavaHome','Path','InstallationPath','Home'):
                                try:
                                    value,_=winreg.QueryValueEx(key,value_name)
                                    if isinstance(value,str):homes.append(Path(os.path.expandvars(value)))
                                except OSError:pass
                            if depth<4:
                                for index in range(min(winreg.QueryInfoKey(key)[0],64)):
                                    pending.append((name+'\\'+winreg.EnumKey(key,index),depth+1))
                    except OSError:continue
    return homes


def _search_roots(extra_roots=()):
    roots=[Path(p) for p in COMMON_JAVA_ROOTS]
    home=Path.home()
    for variable in ('ProgramFiles','ProgramFiles(x86)','ProgramW6432','LOCALAPPDATA'):
        base=os.environ.get(variable)
        if not base:continue
        for folder in ('Java','Eclipse Adoptium','AdoptOpenJDK','Microsoft','Zulu','BellSoft','Amazon Corretto','Semeru','JetBrains/Toolbox/apps','Programs/Eclipse Adoptium','Programs/Java'):
            roots.append(Path(base)/folder)
    roots.extend([app_root()/'runtime',home/'.jdks',home/'.sdkman/candidates/java',home/'.jabba/jdk',home/'scoop/apps',home/'.minecraft/runtime'])
    for variable in ('APPDATA','LOCALAPPDATA'):
        base=os.environ.get(variable)
        if base:
            roots.extend([Path(base)/'.minecraft/runtime',Path(base)/'HMCL/java',Path(base)/'.hmcl/java'])
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA'])/'Packages/Microsoft.4297127D64EC6_8wekyb3d8bbwe/LocalCache/Local/runtime')
    for variable in ('ProgramFiles','ProgramFiles(x86)'):
        if os.environ.get(variable):roots.append(Path(os.environ[variable])/'Minecraft Launcher/runtime')
    if os.name!='nt':roots.extend([Path('/usr/lib/jvm'),Path('/usr/java'),Path('/Library/Java/JavaVirtualMachines'),home/'Library/Java/JavaVirtualMachines'])
    roots.extend(Path(p) for p in extra_roots if p)
    return roots


def _candidate_paths(extra_roots=(),cancel_event=None) -> list[Path]:
    """Inspect known Java locations to bounded depth; never scan entire drives."""
    result=[];seen=set();visited=set()
    def add(path):
        try:
            if path.is_file():
                real=path.resolve();key=os.path.normcase(str(real))
                if key not in seen:seen.add(key);result.append(real)
        except (OSError,ValueError):pass
    for variable in ('JAVA_HOME','JDK_HOME','JRE_HOME'):
        if os.environ.get(variable):
            base=Path(os.path.expandvars(os.environ[variable].strip('"')));candidate=_java_binary_in(base)
            if candidate:add(candidate)
    for part in os.environ.get('PATH','').split(os.pathsep):
        if part:
            base=Path(os.path.expandvars(part.strip('"')))
            # Oracle's redirect stubs may fail outside their original directory.
            if 'common files/oracle/java' not in str(base).replace('\\','/').lower():add(base/('java.exe' if os.name=='nt' else 'java'))
    roots=_registry_homes()+_search_roots(extra_roots)
    for root in roots:
        pending=[(root,0)];budget=0
        while pending and budget<1200 and len(result)<256:
            if cancel_event is not None and cancel_event.is_set():return result
            directory,depth=pending.pop();budget+=1
            try:
                key=os.path.normcase(str(directory.resolve()))
                if key in visited:continue
                visited.add(key)
                if not directory.is_dir():continue
                binary=_java_binary_in(directory)
                if binary:add(binary);continue
                # JDK bundles on macOS and IntelliJ/JBR use these known layouts.
                for suffix in ('Contents/Home','jre','jbr'):
                    binary=_java_binary_in(directory/suffix)
                    if binary:add(binary)
                if depth<5:
                    for child in directory.iterdir():
                        if child.name.lower() not in ('lib','legal','include','jmods','demo','sample','src','logs','cache') and child.is_dir():pending.append((child,depth+1))
            except (OSError,ValueError):continue
    return result


def _rank(info):
    native=platform.machine().lower()
    architecture=info.architecture
    compatible=(not architecture or (architecture in ('aarch64','arm64'))==('arm' in native))
    version=tuple(int(x) for x in re.findall(r'\d+',info.version))
    return (compatible,info.bits!=32,version,str(info.path).lower())


def find_all_java(extra_roots=(),*,refresh=False,cancel_event=None,on_progress=None) -> list[JavaInfo]:
    """Probe distinct executables concurrently; retain different installations."""
    paths=_candidate_paths(extra_roots,cancel_event);result=[]
    with ThreadPoolExecutor(max_workers=6,thread_name_prefix='onion-java') as pool:
        futures=[pool.submit(probe_java,path,refresh=refresh) for path in paths]
        for index,future in enumerate(futures):
            if cancel_event is not None and cancel_event.is_set():
                for pending in futures:pending.cancel()
                break
            info=future.result()
            if info:result.append(info)
            if on_progress:on_progress(index+1,len(paths))
    return sorted(result,key=lambda info:(info.major,_rank(info)),reverse=True)


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
        return max(exact,key=_rank)
    newer = sorted((j for j in candidates if j.major > required), key=lambda j: j.major)
    if newer:
        return newer[0]
    return max(candidates, key=lambda j: j.major)


def resolve_java(required, explicit: str, downloader,
                 on_stage=None, on_progress=None, *, search_roots=(), cancel_event=None):
    """确定用于启动的 Java。

    策略：显式指定 > 本机精确大版本命中 > 自动下载精确大版本；
    找不到精确版本时返回 None（由调用方报错），不再回退到较新/任意版本，
    避免 Java 大版本不兼容导致游戏无法启动。
    """
    if explicit:
        info = probe_java(Path(explicit))
        if info:
            return info
    candidates = find_all_java(search_roots,cancel_event=cancel_event)
    if required is None:
        # 版本未声明 Java 需求时，取本机最高版本
        return max(candidates, key=lambda x: x.major) if candidates else None
    exact = max((c for c in candidates if c.major == required), key=_rank, default=None)
    if exact:
        return exact
    if cancel_event is not None and cancel_event.is_set():return None
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
        from .safety import child
        target = child(dest,rel)
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
