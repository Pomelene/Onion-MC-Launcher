# -*- coding: utf-8 -*-
"""存档（世界）识别与备份：解析 level.dat 的 NBT，读取名称/版本/游戏模式。

NBT 只用标准库实现（gzip + 大端读取），不做完整规范，覆盖 level.dat 需要的标签类型。
"""

import gzip
import os
import shutil
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

GAME_MODES = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}


class _NbtReader:
    """最小 NBT 读取器。"""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.remaining=16*1024**2
        self.tags=0

    def _read(self, size: int) -> bytes:
        if size<0 or size>self.remaining:raise ValueError('NBT 数据超过安全上限')
        self.remaining-=size
        data = self.stream.read(size)
        if len(data) != size:
            raise ValueError("NBT 数据不完整")
        return data

    def _string(self) -> str:
        length = struct.unpack(">H", self._read(2))[0]
        return self._read(length).decode("utf-8", errors="replace")

    def payload(self, tag_type: int,depth=0):
        self.tags+=1
        if depth>64 or self.tags>1_000_000:raise ValueError('NBT 结构超过安全上限')
        if tag_type == TAG_BYTE:
            return struct.unpack(">b", self._read(1))[0]
        if tag_type == TAG_SHORT:
            return struct.unpack(">h", self._read(2))[0]
        if tag_type == TAG_INT:
            return struct.unpack(">i", self._read(4))[0]
        if tag_type == TAG_LONG:
            return struct.unpack(">q", self._read(8))[0]
        if tag_type == TAG_FLOAT:
            return struct.unpack(">f", self._read(4))[0]
        if tag_type == TAG_DOUBLE:
            return struct.unpack(">d", self._read(8))[0]
        if tag_type == TAG_BYTE_ARRAY:
            length = struct.unpack(">i", self._read(4))[0]
            return self._read(length)
        if tag_type == TAG_STRING:
            return self._string()
        if tag_type == TAG_LIST:
            item_type = struct.unpack(">b", self._read(1))[0]
            length = struct.unpack(">i", self._read(4))[0]
            if length<0 or length>1_000_000:raise ValueError('NBT 列表超过安全上限')
            return [self.payload(item_type,depth+1) for _ in range(length)]
        if tag_type == TAG_COMPOUND:
            result = {}
            while True:
                child_type = struct.unpack(">b", self._read(1))[0]
                if child_type == TAG_END:
                    return result
                name = self._string()
                result[name] = self.payload(child_type,depth+1)
        if tag_type == TAG_INT_ARRAY:
            length = struct.unpack(">i", self._read(4))[0]
            if length<0 or length>1_000_000:raise ValueError('NBT 数组超过安全上限')
            return list(struct.unpack(f">{length}i", self._read(4*length)))
        if tag_type == TAG_LONG_ARRAY:
            length = struct.unpack(">i", self._read(4))[0]
            if length<0 or length>1_000_000:raise ValueError('NBT 数组超过安全上限')
            return list(struct.unpack(f">{length}q", self._read(8*length)))
        raise ValueError(f"未知 NBT 类型：{tag_type}")

    def root(self) -> dict:
        tag_type = struct.unpack(">b", self._read(1))[0]
        if tag_type != TAG_COMPOUND:
            raise ValueError("level.dat 根标签不是 Compound")
        self._string()  # 根名，通常为空
        return self.payload(TAG_COMPOUND)


def read_level_dat(path: Path) -> dict:
    """读取 level.dat，返回其中的 Data 复合标签（失败返回空字典）。"""
    try:
        with gzip.open(path, "rb") as stream:
            root = _NbtReader(stream).root()
    except (OSError, ValueError, struct.error):
        return {}
    data = root.get("Data")
    return data if isinstance(data, dict) else root


@dataclass
class WorldInfo:
    """一个存档。"""

    dir: Path
    name: str
    version: str = ""
    game_mode: str = ""
    last_played: float = 0.0
    size: int = 0
    has_icon: bool = False
    hardcore: bool = False

    @property
    def folder(self) -> str:
        return self.dir.name

    def last_played_text(self) -> str:
        if not self.last_played:
            return "未知"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.last_played / 1000.0))

    def size_text(self) -> str:
        value = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024.0
        return f"{value:.1f} GB"


def _dir_size(path: Path) -> int:
    """递归统计目录大小；用 os.scandir 拿到带缓存属性的条目，比 rglob+stat 快。"""
    total = 0
    stack = [Path(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def world_from_dir(world_dir: Path, with_size: bool = True) -> Optional[WorldInfo]:
    level = world_dir / "level.dat"
    if not level.is_file():
        return None
    data = read_level_dat(level)
    version = data.get("Version") if isinstance(data.get("Version"), dict) else {}
    game_type = data.get("GameType")
    info = WorldInfo(
        dir=world_dir,
        name=str(data.get("LevelName") or world_dir.name),
        version=str((version or {}).get("Name") or data.get("Version") or ""),
        game_mode=GAME_MODES.get(game_type if isinstance(game_type, int) else -1, ""),
        last_played=float(data.get("LastPlayed") or 0),
        has_icon=(world_dir / "icon.png").is_file(),
        hardcore=bool(data.get("hardcore") or 0),
    )
    if with_size:
        info.size = _dir_size(world_dir)
    return info


def list_worlds(saves_dir: Path, with_size: bool = True) -> list[WorldInfo]:
    """列出存档目录下的全部世界。"""
    saves_dir = Path(saves_dir)
    if not saves_dir.is_dir():
        return []
    worlds = []
    for entry in saves_dir.iterdir():
        if not entry.is_dir():
            continue
        info = world_from_dir(entry, with_size)
        if info is not None:
            worlds.append(info)
    worlds.sort(key=lambda w: w.last_played, reverse=True)
    return worlds


def backup_world(world: WorldInfo, backups_dir: Path) -> Path:
    """把世界目录打包为 zip，返回备份路径。"""
    import zipfile
    import uuid

    backups_dir = Path(backups_dir)
    if backups_dir.resolve().is_relative_to(world.dir.resolve()):
        raise ValueError("备份目录不能位于存档内部")
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backups_dir / f"{world.folder}-{stamp}-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in world.dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(world.dir.parent))
    return target


def export_world(world: WorldInfo, destination: Path, cancel=None) -> Path:
    """Export a world as a ZIP, publishing only after a complete copy."""
    import stat
    import tempfile
    import zipfile
    from .safety import contained

    source = Path(world.dir)
    destination = Path(destination)
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError('导出文件不能位于世界目录内部')
    contained(source / 'level.dat', source)
    if not (source / 'level.dat').is_file():
        raise ValueError('世界缺少 level.dat')
    fd, temp_name = tempfile.mkstemp(prefix='.onion-world-', suffix='.zip', dir=destination.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for root, dirs, files in os.walk(source, followlinks=False):
                for name in dirs + files:
                    path = Path(root) / name
                    info = path.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                        raise ValueError(f'世界包含无法安全导出的链接：{path}')
                for name in files:
                    if cancel is not None and cancel.is_set():raise RuntimeError('导出已取消')
                    path = Path(root) / name
                    if name == 'session.lock':continue
                    archive.write(path, path.relative_to(source.parent))
        if cancel is not None and cancel.is_set():raise RuntimeError('导出已取消')
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def delete_world(world: WorldInfo) -> None:
    from .safety import recycle
    recycle(world.dir, world.dir.parent)
