# -*- coding: utf-8 -*-
"""外部（参考）实例：识别、预检、沙箱准备与只读指纹。

安全约定：参考目录（如 F:\\.minecraft）全程只读。
- 库通过 classpath 直接引用参考目录中的 jar，不复制、不下载；
- 资源通过 --assetsDir 指向参考 assets（游戏运行期只读）；
- 游戏写入通过 --gameDir 指向工作区沙箱；
- 任何写入参考目录的尝试都会被 repository.assert_writable 拒绝。
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .libraries import Library

#: 沙箱中直接复制的目录（体积小、运行时可能被改写）
COPY_DIRS = ("config", "datapacks", "mods")
#: 体积大但运行期只读的目录：超预算时改用目录联接（junction）
LINK_DIRS = ("resourcepacks", "shaderpacks")
#: 需要复制的根文件
COPY_FILES = ("options.txt", "optionsof.txt", "optionsshaders.txt", "servers.dat")
#: 沙箱中新建的空目录（避免写回参考目录）
EMPTY_DIRS = ("saves", "logs", "crash-reports", "screenshots")


@dataclass
class InstanceInfo:
    """参考目录中的一个版本/实例。"""

    id: str
    dir: Path
    has_json: bool = True
    has_jar: bool = False
    loader: str = ""
    loader_version: str = ""
    java_major: Optional[int] = None
    library_count: int = 0
    mod_count: int = 0
    runnable: bool = True
    reason: str = ""


@dataclass
class PreflightReport:
    """试运行前的可行性检查结果。"""

    instance_id: str
    libraries_total: int = 0
    libraries_workspace: int = 0
    libraries_reference: int = 0
    libraries_missing: list[str] = field(default_factory=list)
    asset_index: str = ""
    asset_total: int = 0
    asset_missing: int = 0
    assets_in_reference: bool = False
    java_major: Optional[int] = None
    ok: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class Sandbox:
    """一次试运行使用的可写沙箱。"""

    path: Path
    copied: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    bytes_copied: int = 0


# ---------------------------------------------------------------- 工具函数

def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _dir_size(Path(entry.path))
    except OSError:
        pass
    return total


def _detect_loader(raw: str) -> tuple[str, str]:
    """从版本 JSON 文本推断加载器与版本号。"""
    low = raw.lower()
    for key, name in (("fabric-loader", "fabric"), ("quilt-loader", "quilt"),
                      ("neoforge", "neoforge"), ("forge", "forge"),
                      ("optifine", "optifine")):
        if key not in low:
            continue
        version = ""
        marker = "net.fabricmc:fabric-loader:" if key == "fabric-loader" else (
            "org.quiltmc:quilt-loader:" if key == "quilt-loader" else "")
        if marker:
            pos = raw.find(marker)
            if pos >= 0:
                version = raw[pos + len(marker):].split('"')[0]
        if not version:
            for token in ("neoforge:", "forge:"):
                pos = low.find(token)
                if pos >= 0:
                    version = raw[pos + len(token):].split('"')[0].split("-")[0]
                    break
        return name, version
    return "", ""


def detect_instances(versions_root: Path) -> list[InstanceInfo]:
    """扫描参考目录的 versions/，返回全部实例（含不可启动的）。"""
    root = Path(versions_root)
    found: list[InstanceInfo] = []
    if not root.is_dir():
        return found
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        json_path = entry / f"{entry.name}.json"
        inst = InstanceInfo(id=entry.name, dir=entry)
        if not json_path.exists():
            inst.has_json = False
            inst.runnable = False
            inst.reason = "缺少版本 JSON"
            found.append(inst)
            continue
        inst.has_jar = (entry / f"{entry.name}.jar").exists()
        try:
            raw = json_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            inst.runnable = False
            inst.reason = f"版本 JSON 解析失败：{exc}"
            found.append(inst)
            continue
        inst.library_count = len(data.get("libraries") or [])
        major = (data.get("javaVersion") or {}).get("majorVersion")
        inst.java_major = int(major) if major else None
        inst.loader, inst.loader_version = _detect_loader(raw)
        mods = entry / "mods"
        if mods.is_dir():
            inst.mod_count = sum(1 for f in mods.glob("*.jar"))
        found.append(inst)
    return found


def _index_coverage(index_path: Path, assets_root: Path) -> tuple[int, int]:
    """返回 (对象总数, 缺失数)。"""
    try:
        raw = json.loads(Path(index_path).read_text(encoding="utf-8"))
        objects = raw.get("objects") or {}
    except (OSError, json.JSONDecodeError):
        return 0, 0
    root = Path(assets_root) / "objects"
    buckets: dict[str, set[str]] = {}
    for meta in objects.values():
        h = str(meta.get("hash") or "")
        if len(h) < 2:
            continue
        buckets.setdefault(h[:2], set()).add(h)
    missing = 0
    for bucket, hashes in buckets.items():
        directory = root / bucket
        if not directory.is_dir():
            missing += len(hashes)
            continue
        try:
            names = {e.name for e in os.scandir(directory) if e.is_file()}
        except OSError:
            missing += len(hashes)
            continue
        missing += len(hashes - names)
    return len(objects), missing


def preflight(repo, ref_root: Path, inst: InstanceInfo) -> PreflightReport:
    """检查库、资源与 Java 是否足以启动该实例（不写任何文件）。"""
    report = PreflightReport(instance_id=inst.id, java_major=inst.java_major)
    if not inst.runnable:
        report.ok = False
        report.notes.append(inst.reason or "实例不可运行")
        return report
    json_path = inst.dir / f"{inst.id}.json"
    try:
        data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        report.ok = False
        report.notes.append(f"读取版本 JSON 失败：{exc}")
        return report

    libraries = [Library.from_json(x) for x in (data.get("libraries") or [])]
    usable = [lib for lib in libraries if lib.matches({})]
    report.libraries_total = len(usable)
    ref_libs = Path(ref_root) / "libraries"
    for lib in usable:
        rel = lib.native_path() if lib.is_native() else lib.artifact_path()
        if not rel:
            report.libraries_missing.append(lib.name)
            continue
        if (repo.libraries_dir / rel).is_file():
            report.libraries_workspace += 1
        elif (ref_libs / rel).is_file():
            report.libraries_reference += 1
        else:
            report.libraries_missing.append(lib.name)

    index_id = (data.get("assetIndex") or {}).get("id", "")
    report.asset_index = index_id
    if index_id:
        ref_assets = Path(ref_root) / "assets"
        index_path = ref_assets / "indexes" / f"{index_id}.json"
        if index_path.exists():
            total, missing = _index_coverage(index_path, ref_assets)
            report.asset_total = total
            report.asset_missing = missing
            report.assets_in_reference = missing == 0 and total > 0
        else:
            report.notes.append(f"参考目录缺少资源索引 {index_id}.json")

    if report.libraries_missing:
        report.ok = False
        preview = ", ".join(report.libraries_missing[:3])
        report.notes.append(f"缺少 {len(report.libraries_missing)} 个库：{preview}")
    if not report.assets_in_reference:
        report.ok = False
        report.notes.append(f"参考资源未完整覆盖索引 {index_id or '(无)'}")
    if inst.java_major is None:
        report.notes.append("版本未声明 javaVersion，将按可用 Java 推断")
    return report


def junction(source: Path, target: Path) -> bool:
    """创建 Windows 目录联接（不需要管理员权限）。"""
    if os.name != "nt":
        return False
    if target.exists():
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(source)],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return target.exists()


def prepare_sandbox(inst: InstanceInfo, sandbox_dir: Path, budget_mb: int = 512) -> Sandbox:
    """构建试运行沙箱：小目录复制、大目录按预算联接、存档不复制。"""
    sandbox = Path(sandbox_dir)
    sandbox.mkdir(parents=True, exist_ok=True)
    result = Sandbox(path=sandbox)
    budget = max(0, int(budget_mb)) * 1024 * 1024

    for name in COPY_DIRS:
        source = inst.dir / name
        if not source.is_dir():
            continue
        size = _dir_size(source)
        if budget and result.bytes_copied + size > budget:
            raise RuntimeError(f"沙箱复制预算不足：{name}；请增加 sandbox_budget_mb")
        try:
            shutil.copytree(source, sandbox / name, dirs_exist_ok=True)
            result.copied.append(name)
            result.bytes_copied += size
        except OSError:
            continue

    for name in LINK_DIRS:
        source = inst.dir / name
        if not source.is_dir():
            continue
        size = _dir_size(source)
        if not budget or result.bytes_copied + size <= budget:
            try:
                shutil.copytree(source, sandbox / name, dirs_exist_ok=True)
                result.copied.append(name)
                result.bytes_copied += size
                continue
            except OSError:
                pass
        raise RuntimeError(f"沙箱复制预算不足或复制失败：{name}；不使用可写目录联接")

    for name in COPY_FILES:
        source = inst.dir / name
        if source.is_file():
            try:
                shutil.copy2(source, sandbox / name)
                result.copied.append(name)
                result.bytes_copied += source.stat().st_size
            except OSError:
                continue

    for name in EMPTY_DIRS:
        (sandbox / name).mkdir(parents=True, exist_ok=True)
    return result


def detect_mod_java_requirement(mods_dir: Path, limit: int = 60) -> Optional[int]:
    """扫描模组的 fabric.mod.json，推断所需的最低 Java 大版本。

    版本 JSON 没有 javaVersion 时（自定义整合包常见），模组元数据是唯一可靠来源。
    """
    import re
    import zipfile

    mods_dir = Path(mods_dir)
    if not mods_dir.is_dir():
        return None
    required: list[int] = []
    for jar in sorted(mods_dir.glob("*.jar"))[:limit]:
        try:
            with zipfile.ZipFile(jar) as archive:
                if "fabric.mod.json" not in archive.namelist():
                    continue
                text = archive.read("fabric.mod.json").decode("utf-8", errors="replace")
        except (OSError, zipfile.BadZipFile):
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        depends = data.get("depends") or {}
        value = depends.get("java") if isinstance(depends, dict) else None
        if not value:
            continue
        for token in re.findall(r"(\d{2,})", str(value)):
            required.append(int(token))
    return max(required) if required else None


def fingerprint(root: Path) -> dict[str, tuple[int, int]]:
    """目录指纹：相对路径 -> (字节数, mtime_ns)，用于证明参考目录未被改动。"""
    result: dict[str, tuple[int, int]] = {}
    root = Path(root)
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = Path(base) / name
            try:
                st = path.stat()
            except OSError:
                continue
            result[str(path.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return result


def diff_fingerprints(before: dict, after: dict) -> dict[str, list[str]]:
    """比较两次指纹，返回新增/删除/改动。"""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {"added": added, "removed": removed, "changed": changed}
