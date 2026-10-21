# -*- coding: utf-8 -*-
import tempfile
from pathlib import Path

from launcher.assets import AssetIndex, ensure_virtual_assets

H = "ab" * 20  # 40 位假 hash


def test_parse_and_jobs_skip_existing():
    idx = AssetIndex.parse({"objects": {"a": {"hash": H, "size": 5}}}, "12", "http://x")
    assert idx.virtual is False
    with tempfile.TemporaryDirectory() as d:
        objdir = Path(d)
        assert len(idx.jobs(objdir)) == 1
        p = objdir / "ab" / H
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"12345")  # 尺寸一致 → 跳过
        assert len(idx.jobs(objdir)) == 0


def test_virtual_mapping():
    idx = AssetIndex.parse({"objects": {"a": {"hash": H, "size": 5}}, "virtual": True}, "legacy", "http://x")
    with tempfile.TemporaryDirectory() as d:
        game = Path(d)
        src = game / "assets" / "objects" / "ab" / H
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"12345")
        ensure_virtual_assets(game, idx)
        assert (game / "assets" / "virtual" / "legacy" / "a").read_bytes() == b"12345"
