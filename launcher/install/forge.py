# -*- coding: utf-8 -*-
"""Forge / NeoForge 安装。

做法：下载官方安装器 jar，用其无界面模式（--installClient）安装到游戏目录，
安装器会生成版本 JSON 与必要文件，随后交给常规安装流程补全依赖。
"""

import re
import json
import shutil
import tempfile
import zipfile
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from ..download import DownloadError, DownloadJob
from ..safety import contained, write_text

FORGE_MAVEN = "https://maven.minecraftforge.net"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases"


def _parse_metadata(xml_text: str) -> list[str]:
    """解析 maven-metadata.xml 中的版本号列表。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    return [node.text.strip() for node in root.iter("version") if node.text]


def _version_key(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text))


def list_versions(repo, kind: str, game_version: str) -> list[str]:
    """列出某游戏版本可用的 Forge/NeoForge 版本（新→旧）。

    版本列表优先取官方 maven（镜像的 metadata 可能过期），失败再用 BMCL 接口。
    """
    if kind == "neoforge":
        if game_version.startswith("1.20.1"):
            url = f"{NEOFORGE_MAVEN}/net/neoforged/forge/maven-metadata.xml"
            prefix = f"{game_version}-"
        else:
            url = f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/maven-metadata.xml"
            prefix = ".".join(game_version.split(".")[1:3]) + "."
        try:
            versions = _parse_metadata(repo.downloader.fetch(url))
            return sorted((v for v in versions if v.startswith(prefix)),
                          key=_version_key, reverse=True)
        except Exception:  # noqa: BLE001
            return []
    try:
        versions = _parse_metadata(repo.downloader.fetch(
            f"{FORGE_MAVEN}/net/minecraftforge/forge/maven-metadata.xml"))
        prefix = f"{game_version}-"
        found = sorted((v for v in versions if v.startswith(prefix)),
                       key=_version_key, reverse=True)
        if found:
            return found
    except Exception:  # noqa: BLE001
        pass
    # 回退：BMCL 的 forge 版本接口
    try:
        data = repo.downloader.fetch_json(
            f"https://bmclapi2.bangbang93.com/forge/minecraft/{game_version}")
    except Exception:  # noqa: BLE001
        return []
    versions = [f"{game_version}-{item.get('version')}" for item in data if item.get("version")]
    return sorted(versions, key=_version_key, reverse=True)


def _installer_info(kind: str, game_version: str, version: str) -> tuple[str, str]:
    """返回 (installer 相对路径, 下载 URL)。"""
    if kind == "neoforge" and not game_version.startswith("1.20.1"):
        rel = f"net/neoforged/neoforge/{version}/neoforge-{version}-installer.jar"
        return rel, f"{NEOFORGE_MAVEN}/{rel}"
    if kind == "neoforge":
        rel = f"net/neoforged/forge/{version}/forge-{version}-installer.jar"
        return rel, f"{NEOFORGE_MAVEN}/{rel}"
    rel = f"net/minecraftforge/forge/{version}/forge-{version}-installer.jar"
    return rel, f"{FORGE_MAVEN}/{rel}"


def install_forge(repo, game_version: str, kind: str = "forge",
                  version: str = "", on_stage=None, on_progress=None,
                  java_path: str = "") -> str:
    """安装 Forge/NeoForge，返回生成的版本 id。"""
    def stage(text: str) -> None:
        if on_stage:
            on_stage(text)

    repo.assert_writable(repo.game_dir / ".onion")

    stage(f"查询 {kind} 版本列表")
    if not version:
        versions = list_versions(repo, kind, game_version)
        if not versions:
            raise DownloadError(f"找不到适配 {game_version} 的 {kind} 版本")
        version = versions[0]

    stage("准备原版客户端")
    if kind == "forge" and not version.startswith(game_version + "-"):
        version = f"{game_version}-{version}"
    repo.install(game_version, on_stage=on_stage, on_progress=on_progress)

    rel, url = _installer_info(kind, game_version, version)
    cache = repo.cache_path('installers')
    installer = cache / Path(rel).name
    stage(f"下载 {kind} 安装器 {version}")
    if not installer.is_file() or not zipfile.is_zipfile(installer):
        try:
            repo.downloader.download_one(
                DownloadJob(repo.remap(url), installer, name=installer.name))
        except Exception:  # noqa: BLE001
            repo.downloader.download_one(DownloadJob(url, installer, name=installer.name))

    # Never expose the real launcher_profiles.json or user instances to an installer.
    staging = repo.cache_path('staging')
    staging.mkdir(parents=True, exist_ok=True)
    java = java_path or _pick_installer_java()
    if not java:
        raise DownloadError("安装加载器需要可用的 Java，请先在设置中指定")
    with tempfile.TemporaryDirectory(prefix=f"{kind}-", dir=staging) as temporary:
        stage_root = Path(temporary)
        (stage_root / "launcher_profiles.json").write_text("{}", encoding="utf-8")
        base = stage_root / "versions" / game_version
        base.mkdir(parents=True)
        for extension in ("json", "jar"):
            source = repo.version_dir(game_version) / f"{game_version}.{extension}"
            if source.is_file():
                shutil.copy2(source, base / source.name)
        # Validate disposable copies of shared libraries, never the user's originals.
        from ..libraries import Library
        prefetch = {}
        with zipfile.ZipFile(installer) as archive:
            for metadata in ("install_profile.json", "version.json"):
                if metadata not in archive.namelist():
                    continue
                profile = json.loads(archive.read(metadata))
                for item in profile.get("libraries", []):
                    library = Library.from_json(item)
                    relative = library.artifact_path()
                    if not relative:
                        continue
                    source = contained(repo.libraries_dir / relative, repo.game_dir)
                    dest = contained(stage_root / "libraries" / relative, stage_root)
                    if source.is_file() and not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
                    embedded = "maven/" + relative.replace("\\", "/")
                    if not dest.exists() and embedded in archive.namelist():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(archive.read(embedded))
                    artifact = (item.get("downloads") or {}).get("artifact") or {}
                    if artifact.get("url"):
                        sha1, size = library.artifact_info()
                        cached = contained(cache / "libraries" / relative, repo.game_dir)
                        if dest.is_file() and not cached.exists():
                            cached.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(dest, cached)
                        prefetch[relative] = DownloadJob(repo.remap(artifact["url"]), cached,
                                                       sha1=sha1, size=size, name=item["name"],
                                                       fallback_urls=(artifact["url"],))
        if prefetch:
            stage(f"预下载安装器依赖（{len(prefetch)} 个，校验已有缓存）")
            repo.download_jobs(list(prefetch.values()), on_progress)
            for relative, job in prefetch.items():
                destination = contained(stage_root / "libraries" / relative, stage_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(job.path, destination)
        stage(f"运行 {kind} 安装器（隔离安装）")
        command = [str(java), "-jar", str(installer), "--installClient", str(stage_root)]
        proc = subprocess.run(command, cwd=str(stage_root), capture_output=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = ((proc.stdout or b"").decode("utf-8", "replace")
                  + (proc.stderr or b"").decode("utf-8", "replace"))
        if proc.returncode != 0:
            raise DownloadError(f"{kind} 安装器执行失败：\n{output[-1800:]}")
        created = [p for p in (stage_root / "versions").iterdir()
                   if p.name != game_version and (p / f"{p.name}.json").is_file()]
        if len(created) != 1:
            raise DownloadError(f"{kind} 安装器生成的版本不明确：{output[-600:]}")
        source = created[0]
        target = repo.assert_writable(repo.version_dir(source.name))
        if target.exists():
            # Reinstallation must preserve existing config/mods/worlds.
            existing = target / f"{source.name}.json"
            if not existing.exists() or json.loads(existing.read_text(encoding="utf-8")) != json.loads(
                    (source / f"{source.name}.json").read_text(encoding="utf-8")):
                raise FileExistsError(f"同名版本已存在，未覆盖：{target}")
        libraries = stage_root / "libraries"
        if libraries.is_dir():
            for file in libraries.rglob("*"):
                if not file.is_file():
                    continue
                dest = repo.assert_writable(repo.libraries_dir / file.relative_to(libraries))
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, dest)
        if not target.exists():
            shutil.copytree(source, target)
        stage(f"{kind} 安装完成：{source.name}")
        return source.name


def _pick_installer_java() -> str:
    """安装器需要可用的 Java：优先 17，其次 8/21，最后取最高版本。"""
    from ..java import find_all_java
    infos = find_all_java()
    if not infos:
        return ""
    preferred = [i for i in infos if i.major in (17, 8, 21)]
    chosen = preferred[0] if preferred else max(infos, key=lambda i: i.major)
    return str(chosen.path)
