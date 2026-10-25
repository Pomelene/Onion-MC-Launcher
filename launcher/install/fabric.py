# -*- coding: utf-8 -*-
"""Fabric / Quilt 加载器安装。

两者都提供"玩家可直接使用的版本 JSON"（profile/json 接口），
其中含 inheritsFrom、mainClass 与加载器库，因此安装非常直接：
下载 profile JSON 保存为新的版本，再走常规安装流程即可。
"""

import json
from urllib.parse import quote
from pathlib import Path
from typing import Optional

from ..download import DownloadError
from ..safety import write_text

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"


def meta_base(kind: str) -> str:
    return QUILT_META if kind == "quilt" else FABRIC_META


def list_loaders(downloader, kind: str, game_version: str) -> list[dict]:
    """列出某游戏版本可用的加载器版本（新的在前）。"""
    url = f"{meta_base(kind)}/versions/loader/{quote(game_version,safe='')}"
    data = downloader.fetch_json(url)
    return data or []


def list_game_versions(downloader, kind: str = "fabric") -> list[dict]:
    """列出加载器支持的游戏版本。"""
    return downloader.fetch_json(f"{meta_base(kind)}/versions/game") or []


def pick_loader(downloader, kind: str, game_version: str,
                loader_version: Optional[str] = None) -> Optional[dict]:
    """选择一个加载器版本：显式指定优先，否则取最新稳定版。"""
    loaders = list_loaders(downloader, kind, game_version)
    if not loaders:
        return None
    if loader_version:
        for entry in loaders:
            if (entry.get("loader") or {}).get("version") == loader_version:
                return entry
        return None
    for entry in loaders:
        if (entry.get("loader") or {}).get("stable"):
            return entry
    return loaders[0]


def install_loader(repo, game_version: str, loader_version: Optional[str] = None,
                   kind: str = "fabric", on_stage=None) -> str:
    """安装 Fabric/Quilt，返回新版本 id（随后由调用方触发 repo.install）。"""
    def stage(text: str) -> None:
        if on_stage:
            on_stage(text)

    stage(f"查询 {kind} 加载器版本")
    entry = pick_loader(repo.downloader, kind, game_version, loader_version)
    if entry is None:
        raise DownloadError(f"找不到适用于 {game_version} 的 {kind} 加载器")
    loader_ver = (entry.get("loader") or {}).get("version", "unknown")
    version_id = f"{kind}-loader-{loader_ver}-{game_version}"

    stage(f"下载 {kind} 加载器配置")
    url = f"{meta_base(kind)}/versions/loader/{quote(game_version,safe='')}/{quote(loader_ver,safe='')}/profile/json"
    profile = repo.downloader.fetch_json(url)

    profile["id"] = version_id
    profile.setdefault("inheritsFrom", game_version)

    target_dir = repo.version_dir(version_id)
    repo.assert_writable(target_dir)
    if (target_dir / f"{version_id}.json").exists():
        return version_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{version_id}.json"
    write_text(target, json.dumps(profile, ensure_ascii=False, indent=2))
    return version_id
