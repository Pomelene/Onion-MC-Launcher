# -*- coding: utf-8 -*-
"""Minecraft 版本模型与解析。

- 拉取并缓存 Mojang 版本清单（version_manifest_v2.json）
- 读取 / 合并单个版本 JSON（含 inheritsFrom 继承链）
- 产出可直接用于下载与启动的"展开版本"
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .libraries import Library
from .rules import evaluate_rules

VERSION_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"


class VersionError(Exception):
    """版本相关错误。"""


class VersionNotFound(VersionError):
    def __init__(self, version_id: str):
        super().__init__(f"版本不存在: {version_id}")
        self.version_id = version_id


@dataclass
class VersionEntry:
    """版本清单中的一条记录。"""

    id: str
    type: str
    url: str
    release_time: str = ""

    @property
    def is_release(self) -> bool:
        return self.type == "release"


class VersionManifest:
    """Mojang 版本清单。"""

    def __init__(self, data: dict):
        self.latest = data.get("latest", {}) or {}
        self.versions: list[VersionEntry] = [
            VersionEntry(v.get("id", ""), v.get("type", ""), v.get("url", ""), v.get("releaseTime", ""))
            for v in data.get("versions", [])
        ]

    @classmethod
    def fetch(cls, downloader, url: Optional[str] = None) -> "VersionManifest":
        data = downloader.fetch_json(url or VERSION_MANIFEST_URL)
        return cls(data)

    def find(self, version_id: str) -> Optional[VersionEntry]:
        for v in self.versions:
            if v.id == version_id:
                return v
        return None

    def snapshot_versions(self) -> list[VersionEntry]:
        """按发布时间倒序的版本列表。"""
        return sorted(self.versions, key=lambda v: v.release_time, reverse=True)


def _resolve_arguments(arguments: Any, features: Optional[dict] = None) -> list[str]:
    """展开 arguments 数组：字符串直接保留，对象按规则求值后取 value 列表。"""
    result: list[str] = []
    for item in arguments or []:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            value = item.get("value")
            if evaluate_rules(item.get("rules"), features):
                if isinstance(value, str):
                    result.append(value)
                elif isinstance(value, list):
                    result.extend(v for v in value if isinstance(v, str))
    return result


@dataclass
class ResolvedVersion:
    """继承合并后的完整版本信息（用于下载与启动）。"""

    id: str = ""
    type: str = "release"
    release_time: str = ""
    main_class: str = ""
    #: 客户端 jar 的下载信息（sha1/size/url）与归属版本 id
    client: dict = field(default_factory=dict)
    client_version_id: str = ""
    jar_id: str = ""            # 版本 JSON 的 jar 字段：显式指定用哪个版本目录的 jar
    #: 资源索引信息（id/sha1/size/total/url）
    asset_index: dict = field(default_factory=dict)
    #: 需要的 Java 大版本号（如 17）；无则 None
    java_major: Optional[int] = None
    #: 日志配置（file/argument/url/sha1/size）
    logging: Optional[dict] = None
    libraries: list[Library] = field(default_factory=list)
    #: 新版 arguments（jvm/game 分离）
    jvm_args: list[str] = field(default_factory=list)
    game_args: list[str] = field(default_factory=list)
    #: 旧版（1.12-）的 minecraftArguments 字符串
    minecraft_args: Optional[str] = None

    @property
    def uses_new_arguments(self) -> bool:
        return not self.minecraft_args and bool(self.jvm_args or self.game_args)

    @property
    def asset_index_id(self) -> str:
        return self.asset_index.get("id") or "legacy"


class VersionResolver:
    """读取本地 versions/ 目录中的版本 JSON 并合并继承链。"""

    def __init__(self, versions_dir: Path):
        self.versions_dir = Path(versions_dir)

    def json_path(self, version_id: str) -> Path:
        from .safety import child
        return child(self.versions_dir, version_id) / f"{version_id}.json"

    def load_raw(self, version_id: str) -> dict:
        p = self.json_path(version_id)
        if not p.exists():
            raise VersionNotFound(version_id)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise VersionError(f"版本 JSON 损坏: {p}: {e}") from e

    def resolve(self, version_id: str, features: Optional[dict] = None) -> ResolvedVersion:
        """沿 inheritsFrom 链向上合并，子版本优先。"""
        chain: list[dict] = []
        seen: set[str] = set()
        own_jar = ""
        cur = version_id
        while cur and cur not in seen:
            seen.add(cur)
            data = self.load_raw(cur)
            if not own_jar and (self.json_path(cur).parent / f"{cur}.jar").is_file():
                own_jar = cur
            chain.append(data)
            cur = data.get("inheritsFrom")
        if cur:
            raise VersionError(f"版本继承存在循环：{cur}")

        rv = ResolvedVersion()
        rv.id = version_id
        rv.jar_id = own_jar
        rv.type = chain[0].get("type") or "release"
        rv.release_time = chain[0].get("releaseTime") or ""

        # 标量字段按“父 → 子”合并，子版本可覆盖父版本（如加载器改写 mainClass）
        for data in reversed(chain):
            if data.get("mainClass"):
                rv.main_class = data["mainClass"]
            d = (data.get("downloads") or {}).get("client")
            if d:
                rv.client = d
                rv.client_version_id = data.get("id") or ""
            if data.get("jar"):
                rv.jar_id = data["jar"]
            if data.get("assetIndex"):
                rv.asset_index = data["assetIndex"]
            if data.get("javaVersion"):
                rv.java_major = data["javaVersion"].get("majorVersion")
            if data.get("logging"):
                rv.logging = (data["logging"] or {}).get("client")

        # 库：子版本在前合并
        libs: list[Library] = []
        for data in chain:
            for item in data.get("libraries", []) or []:
                libs.append(Library.from_json(item))
        rv.libraries = libs

        # 参数：父 → 子顺序合并（子版本可在父版本基础上追加）
        has_arguments = False
        for data in reversed(chain):
            args = data.get("arguments")
            if isinstance(args, dict):
                has_arguments = True
                rv.jvm_args += _resolve_arguments(args.get("jvm"), features)
                rv.game_args += _resolve_arguments(args.get("game"), features)
        if not has_arguments:
            # 旧版：使用最年轻一层提供的 minecraftArguments 字符串
            for data in chain:
                if data.get("minecraftArguments") is not None:
                    rv.minecraft_args = data["minecraftArguments"]
                    break
        return rv

    def list_installed(self) -> list[str]:
        """列出本地已安装的版本 id。"""
        if not self.versions_dir.exists():
            return []
        return sorted(
            (d.name for d in self.versions_dir.iterdir()
             if d.is_dir() and not d.name.startswith('.') and (d / f"{d.name}.json").exists())
        )
