# -*- coding: utf-8 -*-
"""存档解析测试：合成 level.dat 并验证字段。"""

import gzip
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher.worlds import list_worlds, read_level_dat, world_from_dir


def _tag_string(name: str, value: str) -> bytes:
    raw = value.encode("utf-8")
    return b"\x08" + struct.pack(">H", len(name)) + name.encode() + struct.pack(">H", len(raw)) + raw


def _tag_int(name: str, value: int) -> bytes:
    return b"\x03" + struct.pack(">H", len(name)) + name.encode() + struct.pack(">i", value)


def _tag_long(name: str, value: int) -> bytes:
    return b"\x04" + struct.pack(">H", len(name)) + name.encode() + struct.pack(">q", value)


def _tag_compound(name: str, body: bytes) -> bytes:
    return b"\x0a" + struct.pack(">H", len(name)) + name.encode() + body + b"\x00"


def test_level_dat_roundtrip():
    data = (_tag_string("LevelName", "测试世界") + _tag_int("GameType", 1)
            + _tag_long("LastPlayed", 1700000000000)
            + _tag_compound("Version", _tag_string("Name", "1.21.1")))
    payload = _tag_compound("", _tag_compound("Data", data))
    with tempfile.TemporaryDirectory() as tmp:
        saves = Path(tmp) / "saves"
        world = saves / "TestWorld"
        world.mkdir(parents=True)
        with gzip.open(world / "level.dat", "wb") as fh:
            fh.write(payload)
        parsed = read_level_dat(world / "level.dat")
        assert parsed["LevelName"] == "测试世界", parsed
        assert parsed["GameType"] == 1
        info = world_from_dir(world)
        assert info is not None and info.name == "测试世界"
        assert info.game_mode == "创造"
        assert info.version == "1.21.1"
        worlds = list_worlds(saves)
        assert len(worlds) == 1 and worlds[0].folder == "TestWorld"


def test_missing_level_dat():
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "Empty"
        empty.mkdir()
        assert world_from_dir(empty) is None
        assert list_worlds(Path(tmp)) == []