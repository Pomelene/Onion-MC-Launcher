# -*- coding: utf-8 -*-
"""环境诊断：Python / 系统 / Java / 网络 / 磁盘，供 doctor 命令与设置页使用。"""

import platform
import shutil
import sys
import time
import uuid
from pathlib import Path

from .download import Downloader
from .java import find_all_java
from .sources import ALL_SOURCES


def _disk_free(path: Path) -> float:
    """返回路径所在磁盘可用空间 (GB)。"""
    try:
        p = path if path.exists() else (path.anchor if path.anchor else Path.cwd())
        while not p.exists() and p.parent != p:
            p = p.parent
        return round(shutil.disk_usage(p).free / (1024 ** 3), 2)
    except OSError:
        return -1.0


def _writable(path: Path) -> bool:
    """判断目录是否可写（尽量不污染：创建后立即删除探测文件）。"""
    probe = path / f".craftbridge-write-test-{uuid.uuid4().hex}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        with probe.open("x", encoding="utf-8") as stream:
            stream.write("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _network_checks(downloader: Downloader, timeout: int) -> list[dict]:
    """探测各下载源版本清单可达性与延迟。"""
    results = []
    for key, _name in ALL_SOURCES.items():
        from .sources import make_source
        url = make_source(key).version_manifest_url()
        start = time.monotonic()
        ok = False
        try:
            downloader.fetch(url)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        results.append({"source": key, "ok": ok, "ms": round((time.monotonic() - start) * 1000)})
    return results


def run_diagnosis(game_dir: Path, downloader: Downloader) -> dict:
    """汇总诊断结果。"""
    javas = find_all_java()
    return {
        "python": sys.version.split()[0],
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "java": [{"major": i.major, "path": str(i.path), "version": i.version} for i in javas],
        "game_dir": str(game_dir),
        "game_dir_writable": _writable(game_dir),
        "disk_free_gb": _disk_free(game_dir),
        "network": _network_checks(downloader, 8),
    }


def format_diagnosis(d: dict) -> str:
    """把诊断结果格式化为人类可读文本。"""
    out = []
    out.append(f"Python      : {d['python']}")
    out.append(f"系统        : {d['os']}")
    out.append(f"游戏目录    : {d['game_dir']}（可写: {d['game_dir_writable']}，可用 {d['disk_free_gb']} GB）")
    if d["java"]:
        for i in d["java"]:
            out.append(f"Java {i['major']:>3}     : {i['path']}  {i['version']}")
    else:
        out.append("Java        : 未发现")
    out.append("网络        :")
    for n in d["network"]:
        mark = "√" if n["ok"] else "×"
        out.append(f"  {mark} {n['source']:<10} {n['ms']} ms")
    return "\n".join(out)
