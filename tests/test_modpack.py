# -*- coding: utf-8 -*-
import json
import tempfile
import zipfile
from pathlib import Path

from launcher.config import Config
from launcher.download import DownloadError
from launcher.modpack import (_safe_extract, export_mrpack, read_modpack_info)
from launcher.repository import GameRepository


def test_read_mrpack_info():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pack.mrpack"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("modrinth.index.json", json.dumps({
                "name": "Test", "versionId": "1.2",
                "dependencies": {"minecraft": "1.20.4", "fabric-loader": "0.15.0"}}))
        info = read_modpack_info(p)
        assert info.kind == "mrpack"
        assert info.game_version == "1.20.4"
        assert info.loader == "fabric" and info.loader_version == "0.15.0"


def test_read_unknown_raises():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("a.txt", "hi")
        try:
            read_modpack_info(p)
            assert False, "应当抛 DownloadError"
        except DownloadError:
            pass


def test_safe_extract_zip_slip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("overrides/../evil.txt", "bad")
            zf.writestr("overrides/good.txt", "ok")
        with zipfile.ZipFile(p) as zf:
            _safe_extract(zf, "overrides", Path(d) / "out")
        assert (Path(d) / "out" / "good.txt").read_bytes() == b"ok"
        assert not (Path(d) / "evil.txt").exists()


def test_export_produces_valid_mrpack():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = Config(root / "settings.json")
        cfg.set("game_dir", str(root / "game"))
        repo = GameRepository(cfg)
        vdir = repo.version_dir("1.20.4")
        vdir.mkdir(parents=True)
        (vdir / "1.20.4.json").write_text(json.dumps({"id": "1.20.4", "type": "release"}),
                                             encoding="utf-8")
        (vdir / ".isolate").write_text("1", encoding="utf-8")
        mods = vdir / "mods"
        mods.mkdir()
        (mods / "mymod.jar").write_bytes(b"fakejarcontent")
        out = root / "out.mrpack"
        export_mrpack(repo, "1.20.4", out, "TestPack")
        assert out.exists()
        info = read_modpack_info(out)
        assert info.kind == "mrpack" and info.game_version == "1.20.4"
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "modrinth.index.json" in names
            assert any(n.startswith("overrides/mods/mymod.jar") for n in names)
