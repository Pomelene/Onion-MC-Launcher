# -*- coding: utf-8 -*-
"""资源（assets）索引与下载。

资源对象统一存放在 assets/objects/<前2位>/<完整hash>，
索引 JSON 记录对象到真实文件名的映射；老版本还有 virtual 映射。
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .download import DownloadJob, sha1_of

# 资源对象下载基础 URL（官方）
ASSETS_OBJECT_URL = "https://resources.download.minecraft.net/"


@dataclass
class AssetObject:
    """索引里的一个资源对象。"""

    key: str
    hash: str
    size: int

    def object_path(self) -> str:
        import re
        if not re.fullmatch(r"[0-9a-fA-F]{40}", self.hash):
            raise ValueError(f"资源哈希无效：{self.hash}")
        return f"{self.hash[:2]}/{self.hash}"

    def url(self, remap=None) -> str:
        u = ASSETS_OBJECT_URL + self.object_path()
        return remap(u) if remap else u


@dataclass
class AssetIndex:
    """已解析的资源索引。"""

    id: str = ""
    url: str = ""
    virtual: bool = False
    map_to_resources: bool = False
    objects: dict[str, AssetObject] = field(default_factory=dict)
    total: int = 0

    @classmethod
    def parse(cls, data: dict, index_id: str = "", url: str = "") -> "AssetIndex":
        idx = cls(id=index_id, url=url,
                  virtual=bool(data.get("virtual")),
                  map_to_resources=bool(data.get("map_to_resources")),
                  total=int(data.get("total") or 0))
        for key, meta in (data.get("objects") or {}).items():
            idx.objects[key] = AssetObject(key, meta["hash"], int(meta.get("size") or 0))
        return idx

    def asset_index_url(self) -> str:
        return self.url

    def jobs(self, objects_dir: Path, remap=None) -> list[DownloadJob]:
        """生成所有缺失对象的下载任务（尺寸一致视为已存在，避免全量哈希）。"""
        jobs = [];sizes={};seen=set()
        for obj in self.objects.values():
            relative=obj.object_path();prefix=os.path.normcase(relative[:2]);key=os.path.normcase(relative)
            if key in seen:continue
            seen.add(key)
            if prefix not in sizes:
                try:
                    with os.scandir(objects_dir/prefix) as entries:
                        sizes[prefix]={os.path.normcase(entry.name):entry.stat(follow_symlinks=False).st_size for entry in entries if entry.is_file(follow_symlinks=False)}
                except FileNotFoundError:sizes[prefix]={}
            p = objects_dir / relative
            if sizes[prefix].get(os.path.normcase(obj.hash)) == obj.size:
                continue
            jobs.append(DownloadJob(obj.url(remap), p, sha1=obj.hash, size=obj.size,
                                    name=obj.key, fallback_urls=(obj.url(),)))
        return jobs

    def missing_count(self, objects_dir: Path) -> int:
        """缺失 / 损坏的对象数量。"""
        return len(self.jobs(objects_dir))


def ensure_asset_index(game_dir: Path, index: AssetIndex, downloader,
                       progress=None) -> Path:
    """下载索引 JSON 到 assets/indexes/{id}.json（内容为原始 JSON）。"""
    indexes_dir = game_dir / "assets" / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    path = indexes_dir / f"{index.id}.json"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = index.asset_index_url()
    data = downloader.fetch(url)
    path.write_bytes(data)
    return path


def ensure_virtual_assets(game_dir: Path, index: AssetIndex, progress=None) -> None:
    """老版本（virtual）需要 assets/virtual/{index_id}/ 下的可读映射。

    把 objects/ 里下载好的文件按原始文件名复制/硬链接到 virtual 目录。
    """
    if not index.virtual and not index.map_to_resources:
        return
    from .safety import child
    virtual_dir = child(game_dir / "assets" / "virtual", index.id)
    objects_dir = game_dir / "assets" / "objects"
    count = 0
    for key, obj in index.objects.items():
        src = objects_dir / obj.object_path()
        dst = child(virtual_dir, key)
        if not src.exists():
            continue
        if dst.exists() and dst.stat().st_size == obj.size:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(src, dst)
        except OSError:
            continue
        count += 1
        if progress:
            progress(count, len(index.objects))
