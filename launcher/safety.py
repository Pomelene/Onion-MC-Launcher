"""Managed-directory boundaries and recoverable file operations."""

import json
import os
import shutil
import stat
import time
import uuid
from pathlib import Path


def component(name: str) -> str:
    if (not isinstance(name, str) or not name.strip() or name in (".", "..")
            or any(c in name for c in '/\\:<>"|?*') or name.endswith((".", " "))
            or any(ord(c) < 32 for c in name)):
        raise ValueError(f"无效的文件或实例名称：{name!r}")
    if name.split('.')[0].upper() in {"CON", "PRN", "AUX", "NUL", *(
            f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10))}:
        raise ValueError(f"系统保留名称：{name}")
    return name


def contained(path: Path, root: Path) -> Path:
    path, root = Path(path), Path(root)
    # A pending download does not exist yet. Do not resolve its leaf with the
    # Windows non-strict realpath fallback; validate literal components instead.
    if '..' in path.parts:
        raise PermissionError(f"拒绝含上级跳转的写入路径：{path}")
    absolute=Path(os.path.abspath(path));base=Path(os.path.abspath(root))
    if absolute == base or not absolute.is_relative_to(base):
        raise PermissionError(f"路径超出管理范围：{path}（管理目录：{root}）")
    # Inspect from the root downward, before following a directory link. Missing
    # descendants are fine, but existing reparse points must never redirect IO.
    current=base
    for part in (None,*absolute.relative_to(base).parts):
        if part is not None:current=current/part
        try:metadata=current.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise PermissionError(f"拒绝通过目录链接修改文件：{current}")
    return path


def child(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts:
        raise ValueError(f"无效的相对路径：{relative}")
    for part in rel.parts:
        component(part)
    return contained(Path(root) / rel, root)


def recycle(path: Path, parent: Path) -> Path:
    """Move an explicitly selected child to its parent's recovery folder."""
    path = contained(path, parent)
    if path.parent.resolve() != Path(parent).resolve():
        raise PermissionError("只能移除当前目录的直接子项")
    if not path.exists():
        raise FileNotFoundError(path)
    trash = contained(Path(parent) / ".craftbridge-trash", parent)
    trash.mkdir(exist_ok=True)
    target = trash / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{path.name}"
    # Record recovery information before moving; a failed move leaves the source intact.
    record = target.with_name(target.name + ".recovery.json")
    record.write_text(json.dumps({"original": str(path.absolute()), "stored": str(target.absolute())},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    path.rename(target)
    return target


def restore_recycled(target: Path, parent: Path) -> Path:
    trash = Path(parent) / ".craftbridge-trash"
    target = contained(target, trash)
    record = target.with_name(target.name + ".recovery.json")
    data = json.loads(record.read_text(encoding="utf-8"))
    original = contained(Path(data["original"]), parent)
    if original.parent.resolve() != Path(parent).resolve() or original.exists():
        raise FileExistsError(f"恢复位置已存在或无效：{original}")
    target.rename(original)
    record.unlink()
    return original


def backup_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    folder = path.parent / ".craftbridge-backups"
    contained(folder, path.parent).mkdir(exist_ok=True)
    target = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{path.name}"
    shutil.copy2(path, target)
    return target


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    backup_file(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
