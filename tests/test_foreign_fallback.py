# -*- coding: utf-8 -*-
"""只读参考目录回退、写入闸门与启动目录覆盖。"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from launcher.config import Config
from launcher.launch import Account, LaunchSettings, build_command
from launcher.libraries import Library
from launcher.repository import GameRepository

REL = "com/example/demo/1.0/demo-1.0.jar"


def _setup(tmp: Path):
    ref = tmp / "ref"
    jar = ref / "libraries" / REL
    jar.parent.mkdir(parents=True)
    jar.write_bytes(b"jar")
    (ref / "assets" / "indexes").mkdir(parents=True)
    (ref / "assets" / "objects").mkdir(parents=True)
    cfg = Config(tmp / "settings.json")
    cfg.set("game_dir", str(tmp / "game"))
    cfg.set("reference_roots", [str(ref)])
    return ref, jar, GameRepository(cfg), cfg


def test_resolve_library_from_reference():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ref, jar, repo, _cfg = _setup(tmp)
        lib = Library(name="com.example:demo:1.0")
        assert lib.artifact_path() == REL
        path, origin = repo.resolve_library_file(lib)
        assert origin == "reference"
        assert path == jar


def test_workspace_wins_over_reference():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _ref, _jar, repo, _cfg = _setup(tmp)
        local = repo.libraries_dir / REL
        local.parent.mkdir(parents=True)
        local.write_bytes(b"local")
        path, origin = repo.resolve_library_file(Library(name="com.example:demo:1.0"))
        assert origin == "workspace"
        assert path == local


def test_missing_library():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        cfg = Config(tmp / "s2.json")
        cfg.set("game_dir", str(tmp / "game"))
        repo = GameRepository(cfg)
        path, origin = repo.resolve_library_file(Library(name="com.example:demo:1.0"))
        assert path is None and origin == "missing"


def test_write_guard_blocks_reference():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ref, _jar, repo, _cfg = _setup(tmp)
        try:
            repo.assert_writable(ref / "libraries" / "x.jar")
        except PermissionError:
            pass
        else:
            raise AssertionError("应拒绝写入参考目录")
        assert repo.assert_writable(tmp / "game" / "x.jar")


def test_reference_assets_dir():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ref, _jar, repo, _cfg = _setup(tmp)
        assert repo.reference_assets_dir() == ref / "assets"


def test_build_command_overrides():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ref, _jar, repo, _cfg = _setup(tmp)
        rv = SimpleNamespace(
            id="1.20.4", type="release", asset_index_id="5",
            libraries=[], jvm_args=[], game_args=[],
            minecraft_args="--gameDir ${game_directory} --assetsDir ${assets_root}",
            main_class="net.minecraft.client.main.Main",
            client_version_id="1.20.4", client={}, logging=None)
        sandbox = tmp / "sandbox"
        settings = LaunchSettings(game_dir_override=str(sandbox),
                                  assets_dir_override=str(ref / "assets"))
        cmd = build_command(repo, rv, Account(username="Steve", uuid="0" * 32),
                            settings, "java")
        joined = " ".join(cmd)
        assert str(sandbox) in joined
        assert str(ref / "assets") in joined
