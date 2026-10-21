# -*- coding: utf-8 -*-
"""原生库（natives）解压。

原生库 jar 是压缩包，内含 dll/so/dylib 等动态库；
解压到临时 natives 目录供 -Djava.library.path 使用。
"""

import os
import zipfile
from pathlib import Path
from typing import Iterable, Optional

from .libraries import Library
from .archives import validate_archive,copy_member


def _is_excluded(entry_name: str, excludes: Iterable[str]) -> bool:
    """条目是否命中排除列表（顶层前缀匹配）。"""
    for ex in excludes:
        if ex and (entry_name == ex or entry_name.startswith(ex.rstrip("/") + "/")):
            return True
    return False


def extract_native(library: Library, source_jar: Path, dest_dir: Path) -> int:
    """把一个原生库 jar 解压到 dest_dir，返回解压文件数。"""
    if not source_jar.exists():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    excludes = library.exclude_entries()
    count = 0
    with zipfile.ZipFile(source_jar) as zf:
        validate_archive(zf)
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if _is_excluded(name, excludes):
                continue
            if name.startswith("META-INF/"):
                continue
            from .safety import child
            try:
                target = child(dest_dir, name)
            except (ValueError, PermissionError):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_member(zf,info,target)
            count += 1
    return count


def extract_all_natives_from(pairs, natives_dir: Path, on_extract=None) -> int:
    """按 (Library, jar 路径) 解压原生库；jar 可来自只读参考目录。"""
    total = 0
    for lib, jar in pairs:
        if jar and Path(jar).exists():
            n = extract_native(lib, Path(jar), natives_dir)
            total += n
            if on_extract:
                on_extract(lib.name, n)
    return total


def extract_all_natives(native_libs: list[Library], libraries_dir: Path, natives_dir: Path,
                        on_extract=None) -> int:
    """解压一组原生库。返回解压文件总数。"""
    total = 0
    for lib in native_libs:
        jar = lib.native_file(libraries_dir)
        if jar and jar.exists():
            n = extract_native(lib, jar, natives_dir)
            total += n
            if on_extract:
                on_extract(lib.name, n)
    return total
