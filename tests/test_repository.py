# -*- coding: utf-8 -*-
import hashlib
import json
import tempfile
from pathlib import Path

from launcher.config import Config
from launcher.repository import GameRepository


def _repo(root: Path) -> GameRepository:
    cfg = Config(root / "settings.json")
    cfg.set("game_dir", str(root / "game"))
    return GameRepository(cfg)


def test_verify_detects_tamper():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repo = _repo(root)
        vdir = repo.version_dir("x")
        vdir.mkdir(parents=True)
        sha = hashlib.sha1(b"GOOD").hexdigest()
        (vdir / "x.json").write_text(json.dumps({
            "id": "x", "type": "release", "mainClass": "M",
            "downloads": {"client": {"sha1": sha, "size": 4, "url": "http://nope/x.jar"}},
            "assetIndex": {"id": "a", "url": "http://nope/a.json"}}), encoding="utf-8")
        (vdir / "x.jar").write_bytes(b"GOOD")
        index = repo.assets_dir / "indexes" / "a.json"
        index.parent.mkdir(parents=True)
        index.write_text('{"objects":{}}')
        assert repo.verify("x") == []
        assert repo.verify("x", deep=True) == []
        (vdir / "x.jar").write_bytes(b"BAD!")
        probs = repo.verify("x", deep=True)
        assert any("损坏" in p for p in probs)


def test_verify_missing_version():
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        probs = repo.verify("不存在" )
        assert probs and "JSON" in probs[0]


def test_import_external_version_readonly():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ext = root / "ext" / "1.8"
        ext.mkdir(parents=True)
        (ext / "1.8.json").write_text(json.dumps({"id": "1.8"}), encoding="utf-8")
        (ext / "1.8.jar").write_bytes(b"jar")
        repo = _repo(root)
        vid = repo.import_external_version(root / "ext", "1.8")
        assert vid == "1.8"
        assert (repo.version_dir("1.8") / "1.8.json").exists()
        assert (repo.version_dir("1.8") / "1.8.jar").exists()
        assert (ext / "1.8.json").exists()  # 源文件未变


def test_import_external_missing():
    from launcher.version import VersionNotFound
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repo = _repo(root)
        try:
            repo.import_external_version(root / "nope", "1.8")
            assert False
        except VersionNotFound:
            pass
