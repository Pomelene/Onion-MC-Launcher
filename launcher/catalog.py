# -*- coding: utf-8 -*-
"""下载中心：Modrinth 项目搜索、详情、版本选择与文件安装。"""

import json
import urllib.parse
from pathlib import Path

from .download import DownloadJob

MODRINTH_API = "https://api.modrinth.com/v2"

#: 支持的项目类型
KINDS = {"mod": "模组", "resourcepack": "资源包", "shader": "光影", "modpack": "整合包"}


def search(downloader, kind: str, query: str, game_version: str = "",
           loader: str = "", limit: int = 20, offset: int = 0, *, category: str = "", sort: str = "relevance") -> dict:
    """搜索 Modrinth 项目，返回原始响应（含 hits 与 total_hits）。"""
    from .catalog_search import SORTS,search_terms
    if kind not in KINDS:raise ValueError('不支持的项目类型')
    if sort not in {value for _,value in SORTS}:raise ValueError('不支持的排序方式')
    facets = [[f"project_type:{kind}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    if loader:
        facets.append([f"categories:{loader}"])
    if category:
        facets.append([f"categories:{category}"])
    params = {
        "query": search_terms(kind,query), "limit": str(max(1,min(100,int(limit)))), "offset": str(max(0,int(offset))),
        "index": sort, "facets": json.dumps(facets),
    }
    url = f"{MODRINTH_API}/search?" + urllib.parse.urlencode(params)
    return downloader.fetch_json(url)


def categories(downloader,kind):
    """Read the provider's current category tags; never confuse them with loaders."""
    data=downloader.fetch_json(f'{MODRINTH_API}/tag/category')
    return sorted({entry['name'] for entry in data if isinstance(entry,dict)
                   and entry.get('project_type')==kind and isinstance(entry.get('name'),str)})


def project(downloader, project_id: str) -> dict:
    return downloader.fetch_json(f"{MODRINTH_API}/project/{project_id}")


def versions(downloader, project_id: str) -> list[dict]:
    return downloader.fetch_json(f"{MODRINTH_API}/project/{project_id}/version")


def pick_version(version_list: list[dict], game_version: str = "", loader: str = "") -> dict | None:
    """选择第一个适配目标版本与加载器的版本。"""
    for v in version_list:
        if game_version and game_version not in (v.get("game_versions") or []):
            continue
        if loader and loader not in [x.lower() for x in (v.get("loaders") or [])]:
            continue
        return v
    return None


def download_version(downloader, version_obj: dict, target_dir: Path) -> Path:
    """下载该版本的首选文件到 target_dir，返回文件路径。"""
    files = version_obj.get("files") or []
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not primary:
        raise ValueError("该版本没有可下载的文件")
    from .safety import child
    target = child(target_dir, primary["filename"])
    target_dir.mkdir(parents=True, exist_ok=True)
    job = DownloadJob(primary["url"], target,
                      sha1=(primary.get("hashes") or {}).get("sha1"),
                      size=primary.get("size"), name=primary["filename"])
    downloader.download_one(job)
    return target
