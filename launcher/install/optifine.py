# -*- coding: utf-8 -*-
"""OptiFine 安装：复用官方安装器的无界面模式。

OptiFine 安装器（`optifine.Installer`）本身支持命令行启动，但会：
1. 把 `%APPDATA%\\.minecraft` 当作目标目录（不是 `user.home`）；
2. 结束时弹一个 Swing 对话框，无界面环境下抛 HeadlessException（退出码非 0）。

因此这里的做法是：
- 在 `game/optifine/home/<版本>` 下造一个隔离的假 APPDATA，只放入原版 JSON 与 jar；
- 以 `-Djava.awt.headless=true` 运行安装器；
- 以“是否生成新版本目录 + 库文件”判定成功，忽略结尾弹窗导致的退出码；
- 把产物复制回工作区，并清理临时目录。
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..download import DownloadJob
from ..safety import child, backup_file, write_text

#: BMCLAPI 的 OptiFine 索引：/optifine/<mc>；下载：/optifine/<mc>/<type>/<patch>
BMCLAPI_OPTIFINE = "https://bmclapi2.bangbang93.com/optifine"


def list_editions(downloader, mc_version: str) -> list[dict]:
    """列出某游戏版本可用的 OptiFine（稳定版在前，同组内新版本在前）。"""
    data = downloader.fetch_json(f"{BMCLAPI_OPTIFINE}/{mc_version}") or []
    items: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        type_name = str(entry.get("type") or "")
        patch = str(entry.get("patch") or "")
        filename = str(entry.get("filename") or "")
        if not (type_name and patch and filename):
            continue
        items.append({
            "type": type_name,
            "patch": patch,
            "label": f"{type_name}_{patch}",
            "filename": filename,
            "preview": filename.startswith("preview_"),
            "forge": str(entry.get("forge") or ""),
        })
    items.sort(key=lambda item: item["label"], reverse=True)
    items.sort(key=lambda item: item["preview"])
    return items


def pick_edition(downloader, mc_version: str, edition: str = "") -> Optional[dict]:
    """选择 OptiFine 版本：显式指定（如 HD_U_I7）优先，否则取最新稳定版。"""
    items = list_editions(downloader, mc_version)
    if not items:
        return None
    if edition:
        wanted = edition.strip().lower()
        for item in items:
            if item["label"].lower() == wanted or item["filename"].lower() == wanted:
                return item
        return None
    for item in items:
        if not item["preview"]:
            return item
    return items[0]


def _download_installer(repo, mc_version: str, edition: dict,
                        on_progress=None) -> Path:
    filename = edition["filename"]
    target = child(child(repo.cache_path('optifine'), mc_version), filename)
    repo.assert_writable(target)
    if target.is_file() and target.stat().st_size > 1024:
        return target
    url = f"{BMCLAPI_OPTIFINE}/{mc_version}/{edition['type']}/{edition['patch']}"
    target.parent.mkdir(parents=True, exist_ok=True)
    job = DownloadJob(url, target, name=filename)
    repo.downloader.download_one(job)
    return target


def install(repo, mc_version: str, edition: Optional[dict] = None,
            java_path: str = "", on_stage=None, on_progress=None,
            timeout: float = 420.0) -> str:
    """安装 OptiFine 并返回新版本 id。"""
    def stage(text: str) -> None:
        if on_stage:
            on_stage(text)

    stage(f"安装原版 {mc_version}")
    repo.install(mc_version, on_stage=on_stage, on_progress=on_progress)

    if edition is None:
        edition = pick_edition(repo.downloader, mc_version)
    if not edition:
        raise RuntimeError(f"{mc_version} 没有可用的 OptiFine 版本")

    stage(f"下载 OptiFine {edition['label']}")
    installer = _download_installer(repo, mc_version, edition, on_progress)

    if not java_path:
        raise RuntimeError("安装 OptiFine 需要指定 Java 路径")

    stage("准备隔离的安装环境")
    staging = repo.cache_path('staging')
    staging.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="optifine-", dir=staging))
    temp_mc = home / "AppData" / "Roaming" / ".minecraft"
    base_versions = temp_mc / "versions" / mc_version
    base_versions.mkdir(parents=True, exist_ok=True)
    base_dir = Path(repo.version_dir(mc_version))
    for name in (f"{mc_version}.json", f"{mc_version}.jar"):
        source = base_dir / name
        if not source.is_file():
            raise RuntimeError(f"原版文件缺失：{source}")
        shutil.copy2(source, base_versions / name)

    stage("运行 OptiFine 安装器（无界面）")
    env = os.environ.copy()
    env["APPDATA"] = str(temp_mc.parent)
    env["HOME"] = str(home)
    env["user.home"] = str(home)
    command = [str(java_path), "-Djava.awt.headless=true",
               "-cp", str(installer), "optifine.Installer"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              env=env, cwd=str(home),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"OptiFine 安装器超时（{int(timeout)}s）") from exc

    created = []
    versions_dir = temp_mc / "versions"
    if versions_dir.is_dir():
        created = [p for p in versions_dir.iterdir()
                   if p.is_dir() and p.name != mc_version]
    if not created:
        tail = output.strip().splitlines()[-6:]
        raise RuntimeError("OptiFine 安装器没有生成新版本：" + " | ".join(tail))

    source_version = created[0]
    new_id = source_version.name
    stage(f"导入安装结果：{new_id}")
    destination = repo.assert_writable(repo.version_dir(new_id))
    if destination.exists():
        if not (destination / f"{new_id}.json").is_file():
            raise FileExistsError(f"同名目录已存在，未覆盖：{destination}")
    else:
        shutil.copytree(source_version, destination)
    source_libraries = temp_mc / "libraries" / "optifine"
    if source_libraries.is_dir():
        for file in source_libraries.rglob("*"):
            if file.is_file():
                target = repo.assert_writable(repo.libraries_dir / "optifine" / file.relative_to(source_libraries))
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)

    json_path = Path(repo.version_dir(new_id)) / f"{new_id}.json"
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["id"] = new_id
        data.setdefault("type", "release")
        write_text(json_path, json.dumps(data, ensure_ascii=False, indent=2))
    except (OSError, json.JSONDecodeError):
        pass

    shutil.rmtree(home, ignore_errors=True)
    repo.invalidate_library_cache()
    stage("校验 OptiFine 依赖")
    repo.install(new_id, on_stage=on_stage, on_progress=on_progress)
    stage(f"OptiFine 安装完成：{new_id}")
    return new_id
