# -*- coding: utf-8 -*-
"""存档备份、恢复与删除。"""

import shutil
import time
import uuid
import zipfile
import tempfile
import stat
from pathlib import Path


def _zip_dir(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(src.parent))


def _safe_extract(zf: zipfile.ZipFile, target_dir: Path) -> None:
    """解压并防御 zip-slip（路径穿越）。"""
    root = target_dir.resolve()
    for info in zf.infolist():
        from .safety import child
        dest = child(target_dir, info.filename.rstrip('/'))
        if info.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            out.write(src.read())


def backup(save: Path, backups_dir: Path) -> Path:
    """把存档目录压缩到 backups_dir，返回备份文件路径。"""
    if backups_dir.resolve().is_relative_to(save.resolve()):
        raise ValueError("备份目录不能位于存档内部")
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    target = backups_dir / f"{save.name}-{ts}-{uuid.uuid4().hex[:8]}.zip"
    _zip_dir(save, target)
    return target


def restore(zip_path: Path, saves_dir: Path) -> Path:
    """Restore into a new directory, publishing only after a complete extraction.

    Both world-prefixed archives and the launcher's older flat archives are accepted.
    Existing worlds and earlier restores are never merged or overwritten.
    """
    from .safety import child, component, contained
    saves_dir = Path(saves_dir)
    contained(saves_dir / ".craftbridge-restore-probe", saves_dir)
    saves_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        entries = zf.infolist()
        if not entries:
            raise ValueError("备份文件为空")
        flat = any(info.filename == "level.dat" for info in entries)
        root_name = component(Path(zip_path).stem if flat else entries[0].filename.split('/')[0])
        with tempfile.TemporaryDirectory(prefix=".craftbridge-restore-", dir=saves_dir) as temporary:
            staging = Path(temporary) / "world"
            staging.mkdir()
            pending = []
            # Validate every member before extracting any file.
            for info in entries:
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("存档备份不能包含符号链接")
                parts = info.filename.split('/')
                if not flat and parts[0] != root_name:
                    raise ValueError("备份包含多个根目录")
                relative = (info.filename if flat else '/'.join(parts[1:])).rstrip('/')
                if relative:
                    pending.append((info, child(staging, relative)))
            for info, dest in pending:
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, dest.open('wb') as out:
                        shutil.copyfileobj(src, out)
            target = child(saves_dir, root_name)
            while True:
                if target.exists():
                    target = child(saves_dir, f"{root_name}-restored-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}")
                    continue
                try:
                    staging.rename(target)
                    return target
                except FileExistsError:
                    # Windows rename is exclusive; handle a concurrent restore safely.
                    target = child(saves_dir, f"{root_name}-restored-{uuid.uuid4().hex}")


def delete_save(save: Path) -> None:
    from .safety import recycle
    recycle(save, save.parent)
