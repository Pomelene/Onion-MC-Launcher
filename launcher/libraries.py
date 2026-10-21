# -*- coding: utf-8 -*-
"""库（library）的解析：坐标、路径、下载 URL、规则与原生库。

library 在版本 JSON 中的典型形态：
  {
    "name": "com.google.guava:guava:17.0",
    "url": "https://libraries.minecraft.net/",  # 可选，默认官方仓库
    "downloads": {"artifact": {...}, "classifiers": {"natives-windows": {...}}},
    "rules": [...],
    "extract": {"exclude": ["META-INF/"]},
    "natives": {"windows": "natives-windows", ...}
  }
"""

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .rules import evaluate_rules, os_name

DEFAULT_LIBRARY_URL = "https://libraries.minecraft.net/"


def arch_bits() -> str:
    """Mojang 的 ${arch} 取值：32 位架构用 32，其余用 64。"""
    machine = (platform.machine() or "").lower()
    return "32" if machine in ("x86", "i386", "i586", "i686") else "64"


def _fill_arch(text: Optional[str]) -> Optional[str]:
    """替换 classifier 中的 ${arch} 占位符（1.8.9 的 Twitch 原生库会用到）。"""
    if not text:
        return text
    return text.replace("${arch}", arch_bits())


def parse_name(name: str) -> tuple[str, str, str, Optional[str], str]:
    """解析 maven 坐标 "group:artifact:version"（可带 "@扩展名" 或 classifier）。

    返回 (group, artifact, version, classifier, extension)。
    """
    parts = name.split(":")
    if len(parts) == 3:
        group, artifact, version = parts
        classifier = None
    elif len(parts) == 4:
        group, artifact, version, classifier = parts
    else:
        raise ValueError(f"无法解析库坐标: {name}")
    ext = "jar"
    if "@" in version:
        version, ext = version.split("@", 1)
    return group, artifact, version, classifier, ext


def maven_path(name: str, classifier: Optional[str] = None) -> str:
    """由坐标生成仓库内相对路径（如 com/google/guava/guava/17.0/guava-17.0.jar）。"""
    group, artifact, version, name_cls, ext = parse_name(name)
    if classifier is None:
        classifier = name_cls
    base = f"{group.replace(chr(46), chr(47))}/{artifact}/{version}/{artifact}-{version}"
    if classifier:
        base += f"-{classifier}"
    return f"{base}.{ext}"


@dataclass
class Library:
    """一个已解析的库。"""

    name: str
    url: Optional[str] = None
    rules: Optional[list] = None
    extract: Optional[dict] = None
    natives: Optional[dict] = None
    downloads: Optional[dict] = None
    #: 加载器库的顶层校验信息（Fabric meta 用 sha1/size 字段）
    sha1: Optional[str] = None
    size: Optional[int] = None
    #: 加载器（Fabric 等）注入的库，无 Mojang downloads 信息
    is_loader_library: bool = False

    @classmethod
    def from_json(cls, data: Any) -> "Library":
        if isinstance(data, str):
            return cls(name=data, is_loader_library=True)
        return cls(
            name=data.get("name", ""),
            url=data.get("url"),
            rules=data.get("rules"),
            extract=data.get("extract"),
            natives=data.get("natives"),
            downloads=data.get("downloads"),
            sha1=data.get("sha1"),
            size=data.get("size"),
        )

    def matches(self, features: Optional[dict] = None) -> bool:
        return evaluate_rules(self.rules, features)

    def native_classifier(self) -> Optional[str]:
        """当前平台对应的原生库 classifier；无则 None。"""
        if not self.natives:
            return None
        return _fill_arch(self.natives.get(os_name()))

    def is_native(self) -> bool:
        return self.native_classifier() is not None

    # ---------- 仓库相对路径 ----------

    def artifact_path(self) -> str:
        if self.downloads and isinstance(self.downloads.get("artifact"), dict):
            p = self.downloads["artifact"].get("path")
            if p:
                return p
        return maven_path(self.name)

    def native_path(self) -> Optional[str]:
        nd = self.native_download()
        if nd and nd.get("path"):
            return nd["path"]
        cls = self.native_classifier()
        if cls:
            return maven_path(self.name, cls)
        return None

    # ---------- 下载信息 ----------

    def artifact_info(self) -> tuple[Optional[str], Optional[int]]:
        """(sha1, size)：优先 downloads.artifact，其次顶层字段。"""
        a = (self.downloads or {}).get("artifact") or {}
        return a.get("sha1") or self.sha1, a.get("size") or self.size

    def native_download(self) -> Optional[dict]:
        """当前平台原生库的下载信息 dict；无则 None。"""
        cls = self.native_classifier()
        if not cls or not self.downloads:
            return None
        return (self.downloads.get("classifiers") or {}).get(cls)

    def artifact_url(self, remap=None) -> str:
        url = None
        if self.downloads and isinstance(self.downloads.get("artifact"), dict):
            url = self.downloads["artifact"].get("url")
        if not url:
            url = (self.url or DEFAULT_LIBRARY_URL) + self.artifact_path()
        return remap(url) if remap else url

    def native_url(self, remap=None) -> Optional[str]:
        nd = self.native_download()
        url = nd.get("url") if nd else None
        if not url and self.native_path():
            url = (self.url or DEFAULT_LIBRARY_URL) + self.native_path()
        if not url:
            return None
        return remap(url) if remap else url

    # ---------- 其它 ----------

    def exclude_entries(self) -> list[str]:
        """原生库解压时需排除的顶层条目（如 META-INF/）。"""
        return list((self.extract or {}).get("exclude", []) or [])

    def artifact_file(self, libraries_dir: Path) -> Path:
        from .safety import child
        return child(libraries_dir, self.artifact_path())

    def native_file(self, libraries_dir: Path) -> Optional[Path]:
        p = self.native_path()
        from .safety import child
        return child(libraries_dir, p) if p else None
