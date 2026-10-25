# -*- coding: utf-8 -*-
"""模组、资源包、光影与存档管理。

- 扫描目录并读取元数据（fabric.mod.json / mods.toml / mcmod.info / pack.mcmeta）
- 启用 / 禁用（重命名 .jar <-> .jar.disabled）、删除
- 从 Modrinth 搜索并下载模组
"""

import json
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MODRINTH_API = "https://api.modrinth.com/v2"


@dataclass
class ModInfo:
    """一个模组文件。"""

    path: Path
    name: str
    version: str = ""
    mod_id: str = ""
    enabled: bool = True

    @property
    def size_text(self) -> str:
        try:
            size = self.path.stat().st_size
        except OSError:
            return "-"
        if size > 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        return f"{size / 1024:.0f} KB"


def _read_fabric_meta(zf: zipfile.ZipFile) -> Optional[dict]:
    try:
        with zf.open("fabric.mod.json") as f:
            return json.loads(f.read().decode("utf-8-sig", "replace"),strict=False)
    except (KeyError, json.JSONDecodeError, OSError):
        return None


def _read_forge_toml(zf: zipfile.ZipFile) -> Optional[dict]:
    """从 META-INF/mods.toml 中粗略解析 modId / displayName / version。"""
    try:
        text = zf.read("META-INF/mods.toml").decode("utf-8", "replace")
    except (KeyError, OSError):
        return None
    result = {}
    for key in ("modId", "displayName", "version"):
        m = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            result[key] = m.group(1)
    return result or None


def _read_mcmod_info(zf: zipfile.ZipFile) -> Optional[dict]:
    try:
        data = json.loads(zf.read("mcmod.info").decode("utf-8", "replace"))
    except (KeyError, json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict):
        data = data.get("modList") or [data]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        return {"modId": first.get("modid", ""), "displayName": first.get("name", ""),
                "version": first.get("version", "")}
    return None


def read_mod_info(path: Path) -> ModInfo:
    """读取单个模组文件的信息（无元数据时回退到文件名）。"""
    enabled = not path.name.endswith(".disabled")
    info = ModInfo(path=path, name=path.stem.replace(".jar", ""), enabled=enabled)
    try:
        with zipfile.ZipFile(path) as zf:
            meta = _read_fabric_meta(zf) or _read_forge_toml(zf) or _read_mcmod_info(zf)
    except (zipfile.BadZipFile, OSError):
        return info
    if meta:
        info.mod_id = str(meta.get("id") or meta.get("modId") or "")
        info.name = str(meta.get("name") or meta.get("displayName") or info.name)
        info.version = str(meta.get("version") or "")
    return info


def scan_mods(mods_dir: Path) -> list[ModInfo]:
    """扫描模组目录（含已禁用的 .jar.disabled）。"""
    if not mods_dir.exists():
        return []
    result = []
    for p in sorted(mods_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() in (".jar", ".zip") or p.name.endswith(".jar.disabled"):
            result.append(read_mod_info(p))
    return result


def set_mod_enabled(info: ModInfo, enabled: bool) -> ModInfo:
    """启用/禁用一个模组（通过重命名实现，与主流启动器一致）。"""
    if enabled and info.path.name.endswith(".disabled"):
        target = info.path.with_name(info.path.name[: -len(".disabled")])
        if target.exists():
            raise FileExistsError(f"目标文件已存在：{target.name}")
        info.path.rename(target)
        return read_mod_info(target)
    if not enabled and not info.path.name.endswith(".disabled"):
        target = info.path.with_name(info.path.name + ".disabled")
        if target.exists():
            raise FileExistsError(f"目标文件已存在：{target.name}")
        info.path.rename(target)
        return read_mod_info(target)
    return info


def delete_mod(info: ModInfo) -> None:
    """删除模组文件。"""
    from .safety import recycle
    recycle(info.path, info.path.parent)


# ---------------------------------------------------------------- 资源包 / 光影

@dataclass
class PackInfo:
    """资源包或光影包。"""

    path: Path
    name: str
    description: str = ""

    @property
    def size_text(self) -> str:
        try:
            size = self.path.stat().st_size
        except OSError:
            return "-"
        if size > 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        return f"{size / 1024:.0f} KB"


def scan_resourcepacks(pack_dir: Path) -> list[PackInfo]:
    """扫描资源包目录，读取 pack.mcmeta 中的名称与描述。"""
    if not pack_dir.exists():
        return []
    result = []
    for p in sorted(pack_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".zip", ".jar"):
            continue
        info = PackInfo(path=p, name=p.stem)
        try:
            with zipfile.ZipFile(p) as zf:
                meta = json.loads(zf.read("pack.mcmeta").decode("utf-8", "replace"))
            pack = meta.get("pack") or {}
            desc = pack.get("description", "")
            if isinstance(desc, dict):
                desc = desc.get("text", "") or desc.get("translate", "")
            info.description = str(desc)
        except (KeyError, json.JSONDecodeError, OSError, zipfile.BadZipFile):
            pass
        result.append(info)
    return result


def scan_shaderpacks(pack_dir: Path) -> list[PackInfo]:
    """扫描光影包目录。"""
    if not pack_dir.exists():
        return []
    return [PackInfo(path=p, name=p.stem) for p in sorted(pack_dir.iterdir())
            if p.is_file() and p.suffix.lower() in (".zip", ".jar")]


# ---------------------------------------------------------------- 存档

@dataclass
class SaveInfo:
    """一个世界存档（仅取目录名与修改时间）。"""

    path: Path
    name: str
    mtime: float = 0.0


def scan_saves(saves_dir: Path) -> list[SaveInfo]:
    if not saves_dir.exists():
        return []
    result = []
    for p in saves_dir.iterdir():
        if not p.is_dir():
            continue
        if not (p / "level.dat").exists():
            continue
        result.append(SaveInfo(path=p, name=p.name, mtime=(p / "level.dat").stat().st_mtime))
    return sorted(result, key=lambda s: s.mtime, reverse=True)


# ---------------------------------------------------------------- Modrinth

def search_modrinth(downloader, query: str, game_version: str = "",
                    loader: str = "", limit: int = 20) -> list[dict]:
    """搜索 Modrinth 项目，返回 hits 列表。"""
    facets = [["project_type:mod"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    if loader:
        facets.append([f"categories:{loader}"])
    params = {
        "query": query,
        "limit": str(limit),
        "index": "relevance",
        "facets": json.dumps(facets),
    }
    url = f"{MODRINTH_API}/search?" + urllib.parse.urlencode(params)
    data = downloader.fetch_json(url)
    return data.get("hits", [])


def download_modrinth_mod(downloader, project_id: str, mods_dir: Path,
                          game_version: str = "", loader: str = "") -> Path:
    """下载 Modrinth 项目适配当前版本的第一个文件到 mods 目录。"""
    versions = downloader.fetch_json(f"{MODRINTH_API}/project/{project_id}/version")
    candidates = []
    for v in versions:
        if game_version and game_version not in (v.get("game_versions") or []):
            continue
        if loader and loader not in [l.lower() for l in (v.get("loaders") or [])]:
            continue
        candidates.append(v)
    if not candidates:
        raise ValueError("该项目没有适配当前版本的模组文件")
    files = candidates[0].get("files") or []
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not primary:
        raise ValueError("该版本没有可下载的文件")
    target = mods_dir / primary["filename"]
    mods_dir.mkdir(parents=True, exist_ok=True)
    from .download import DownloadJob
    job = DownloadJob(primary["url"], target, sha1=(primary.get("hashes") or {}).get("sha1"),
                      size=primary.get("size"), name=primary["filename"])
    downloader.download_one(job)
    return target

# ---------------------------------------------------------------- 更新 / 依赖 / 重复

def mod_sha1(path: Path) -> str:
    from .download import sha1_of
    return sha1_of(path) or ""


def duplicate_ids(mods: list[ModInfo]) -> list[tuple[str, list[str]]]:
    """找出重复 mod_id（无 mod_id 时用文件名兜底）。"""
    from collections import defaultdict
    groups: dict[str, list[str]] = defaultdict(list)
    for info in mods:
        key = (info.mod_id or info.path.stem).lower()
        groups[key].append(info.name or info.path.name)
    return [(k, v) for k, v in groups.items() if len(v) > 1]


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "Onion Minecraft Launcher/0.1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_updates(downloader, mods: list[ModInfo], game_version: str = "",
                  loader: str = "") -> list[dict]:
    """对每个启用的模组做 SHA-1 反查，返回可更新列表。

    每项：{mod, project_id, current, latest, version_id}。
    """
    updates = []
    for info in mods:
        if not info.enabled:
            continue
        sha1 = mod_sha1(info.path)
        if not sha1:
            continue
        try:
            current = _post_json(f"{MODRINTH_API}/version_file/{sha1}?algorithm=sha1", {})
        except Exception:  # noqa: BLE001
            continue
        project_id = current.get("project_id")
        if not project_id:
            continue
        try:
            versions = downloader.fetch_json(f"{MODRINTH_API}/project/{project_id}/version")
        except Exception:  # noqa: BLE001
            continue
        latest = None
        for v in versions:
            if game_version and game_version not in (v.get("game_versions") or []):
                continue
            if loader and loader not in [x.lower() for x in (v.get("loaders") or [])]:
                continue
            latest = v
            break
        if latest and latest.get("id") != current.get("id"):
            updates.append({
                "mod": info, "project_id": project_id,
                "current": current.get("version_number"),
                "latest": latest.get("version_number"),
                "version_id": latest.get("id"),
            })
    return updates


def install_dependencies(downloader, version_id: str, mods_dir: Path,
                         game_version: str = "", loader: str = "",
                         _depth: int = 0) -> list[Path]:
    """递归安装某 Modrinth 版本的 required 依赖，返回新增文件列表。"""
    from .download import DownloadJob
    if _depth > 6 or not version_id:
        return []
    try:
        data = downloader.fetch_json(f"{MODRINTH_API}/version/{version_id}")
    except Exception:  # noqa: BLE001
        return []
    out: list[Path] = []
    for dep in data.get("dependencies") or []:
        if dep.get("dependency_type") != "required":
            continue
        pid = dep.get("project_id")
        if not pid:
            continue
        try:
            versions = downloader.fetch_json(f"{MODRINTH_API}/project/{pid}/version")
        except Exception:  # noqa: BLE001
            continue
        chosen = next((v for v in versions
                       if (not game_version or game_version in (v.get("game_versions") or []))
                       and (not loader or loader in [x.lower() for x in (v.get("loaders") or [])])), None)
        if not chosen:
            continue
        files = chosen.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary:
            continue
        from .safety import child
        target = child(mods_dir, primary["filename"])
        if target.exists():
            continue
        mods_dir.mkdir(parents=True, exist_ok=True)
        job = DownloadJob(primary["url"], target,
                          sha1=(primary.get("hashes") or {}).get("sha1"),
                          size=primary.get("size"), name=primary["filename"])
        downloader.download_one(job)
        out.append(target)
        out += install_dependencies(downloader, chosen.get("id"), mods_dir,
                                     game_version, loader, _depth + 1)
    return out


def open_in_folder(path: Path) -> None:
    """在系统文件管理器中高亮显示该文件。"""
    import os
    import subprocess
    if os.name == "nt":
        subprocess.run(["explorer", f"/select,{path}"],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        subprocess.run(["xdg-open", str(path.parent)])
