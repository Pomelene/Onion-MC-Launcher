"""Bounded, non-following instance file libraries with recoverable edits."""
import gzip
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from .safety import contained, component, recycle
from .worlds import _NbtReader

SCHEMATICS = {'.litematic', '.schem', '.schematic', '.nbt'}
PICTURES = {'.png', '.jpg', '.jpeg', '.webp'}


@dataclass(frozen=True)
class LibraryEntry:
    path: Path
    directory: bool
    size: int
    modified: float
    detail: str = ''


def checked_folder(root, relative=''):
    root = Path(root)
    if root.is_symlink() or root.is_junction():
        raise PermissionError('管理目录不能是链接')
    return root if not relative else contained(root / relative, root)


def schematic_detail(path):
    try:
        with gzip.open(path, 'rb') as stream:
            data = _NbtReader(stream).root()
        meta = data.get('Metadata', {})
        if not isinstance(meta, dict): return ''
        size = meta.get('EnclosingSize', {})
        dimensions = ' × '.join(str(size[k]) for k in ('x', 'y', 'z')) if isinstance(size, dict) and all(k in size for k in ('x', 'y', 'z')) else ''
        return ' · '.join(str(v) for v in (meta.get('Name', ''), meta.get('Author', ''), dimensions) if v)
    except (OSError, ValueError, struct.error, OverflowError):
        return ''


def scan_library(root, relative='', *, pictures=False):
    folder = checked_folder(root, relative)
    if not folder.exists(): return []
    entries = []
    for path in folder.iterdir():
        if path.name.startswith('.') or path.is_symlink() or path.is_junction(): continue
        contained(path, root)
        directory = path.is_dir()
        if not directory and path.suffix.lower() not in (PICTURES if pictures else SCHEMATICS): continue
        stat = path.stat()
        stamp = stat.st_mtime
        if pictures and not directory:
            try: stamp = datetime.strptime(path.stem[:19], '%Y-%m-%d_%H.%M.%S').timestamp()
            except ValueError: pass
        detail = '' if directory or pictures else schematic_detail(path)
        entries.append(LibraryEntry(path, directory, stat.st_size, stamp, detail))
    entries.sort(key=lambda item: (not item.directory, -item.modified if pictures else item.path.name.casefold(), item.path.name))
    return entries


def import_files(root, relative, sources, *, pictures=False):
    folder = checked_folder(root, relative)
    folder.mkdir(parents=True, exist_ok=True)
    installed = []
    for source in map(Path, sources):
        component(source.name)
        if source.suffix.lower() not in (PICTURES if pictures else SCHEMATICS):
            raise ValueError('不支持的文件类型')
        target = contained(folder / source.name, root)
        if source.resolve() == target.resolve(): continue
        # Exclusive creation: an existing original is never overwritten.
        created = False
        try:
            with source.open('rb') as src, target.open('xb') as dst:
                created = True
                shutil.copyfileobj(src, dst)
            shutil.copystat(source, target)
        except Exception:
            if created: target.unlink(missing_ok=True)
            raise
        installed.append(target)
    return installed


def rename_entry(root, path, name):
    source = contained(Path(path), root)
    target = contained(source.with_name(component(name)), root)
    if source == target: return source
    if target.exists(): raise FileExistsError('同名文件或目录已存在')
    if source.is_file() and target.suffix.lower() != source.suffix.lower():
        raise ValueError('请保留原文件扩展名')
    source.rename(target)
    return target


def remove_entry(root, path):
    source = contained(Path(path), root)
    return recycle(source, source.parent)


def remove_entries(root, paths):
    """Recycle a selection and undo earlier moves if a later one fails."""
    from .safety import restore_recycled
    sources=[contained(Path(path),root) for path in paths]
    if len(set(sources))!=len(sources):raise ValueError('文件选择重复')
    moved=[]
    try:
        for source in sources:moved.append((recycle(source,source.parent),source.parent))
    except Exception as error:
        failures=[]
        for stored,parent in reversed(moved):
            try:restore_recycled(stored,parent)
            except Exception as rollback:failures.append(str(rollback))
        if failures:raise RuntimeError(f'{error}；部分文件未能恢复：'+ '；'.join(failures)) from error
        raise
    return moved


def export_pictures(root, paths, destination):
    destination=Path(destination)
    if not destination.is_dir():raise ValueError('目标文件夹不存在')
    sources=[contained(Path(path),root) for path in paths]
    if any(not path.is_file() or path.suffix.lower() not in PICTURES for path in sources):raise ValueError('只能复制截图文件')
    if len({p.name.casefold() for p in sources})!=len(sources):raise ValueError('选择的截图文件名重复')
    targets=[destination/path.name for path in sources]
    if any(path.exists() for path in targets):raise FileExistsError('目标文件夹中已有同名截图')
    created=[]
    try:
        for source,target in zip(sources,targets):
            with source.open('rb') as inp,target.open('xb') as out:
                created.append(target);shutil.copyfileobj(inp,out)
            shutil.copystat(source,target)
    except Exception:
        for target in created:target.unlink(missing_ok=True)
        raise
    return len(created)
