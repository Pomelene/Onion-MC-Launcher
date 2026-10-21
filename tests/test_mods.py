# -*- coding: utf-8 -*-
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from launcher.mods import ModInfo, duplicate_ids, mod_sha1, scan_mods, set_mod_enabled


def test_duplicate_ids():
    mods = [
        ModInfo(path=Path("a.jar"), name="A", mod_id="m1"),
        ModInfo(path=Path("b.jar"), name="B", mod_id="m1"),
        ModInfo(path=Path("c.jar"), name="C", mod_id="m2"),
    ]
    dups = duplicate_ids(mods)
    assert len(dups) == 1
    assert dups[0][0] == "m1" and len(dups[0][1]) == 2


def test_mod_sha1():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.jar"
        p.write_bytes(b"abc")
        assert mod_sha1(p) == hashlib.sha1(b"abc").hexdigest()
        assert mod_sha1(Path(d) / "nope.jar") == ""


def test_scan_mods_reads_fabric_meta():
    with tempfile.TemporaryDirectory() as d:
        mods_dir = Path(d) / "mods"
        mods_dir.mkdir()
        with zipfile.ZipFile(mods_dir / "mymod.jar", "w") as zf:
            zf.writestr("fabric.mod.json",
                        json.dumps({"id": "mymod", "name": "My Mod", "version": "1.0"}))
        infos = scan_mods(mods_dir)
        assert len(infos) == 1
        assert infos[0].mod_id == "mymod" and infos[0].name == "My Mod"


def test_scan_mods_corrupt_file_fallback():
    with tempfile.TemporaryDirectory() as d:
        mods_dir = Path(d) / "mods"
        mods_dir.mkdir()
        (mods_dir / "broken.jar").write_bytes(b"not a zip")
        infos = scan_mods(mods_dir)
        assert len(infos) == 1 and infos[0].name == "broken"


def test_set_mod_enabled_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        mods_dir = Path(d) / "mods"
        mods_dir.mkdir()
        jar = mods_dir / "m.jar"
        jar.write_bytes(b"x")
        infos = scan_mods(mods_dir)
        disabled = set_mod_enabled(infos[0], False)
        assert not jar.exists() and (mods_dir / "m.jar.disabled").exists()
        assert disabled.enabled is False
        enabled = set_mod_enabled(disabled, True)
        assert jar.exists() and not (mods_dir / "m.jar.disabled").exists()
        assert enabled.enabled is True
