# -*- coding: utf-8 -*-
import json

from launcher.version import VersionResolver


def _write(resolver: VersionResolver, vid: str, data: dict) -> None:
    d = resolver.versions_dir / vid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{vid}.json").write_text(json.dumps(data), encoding="utf-8")


def test_child_main_class_wins(tmp_path=None):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        r = VersionResolver(Path(d))
        _write(r, "1.20.4", {"id": "1.20.4", "mainClass": "net.minecraft.client.main.Main",
                               "downloads": {"client": {"url": "http://x/vanilla.jar", "sha1": "aa"}},
                               "assetIndex": {"id": "12", "url": "http://x/assets"}})
        _write(r, "forge", {"id": "forge", "inheritsFrom": "1.20.4", "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher"})
        rv = r.resolve("forge")
        assert rv.main_class == "cpw.mods.bootstraplauncher.BootstrapLauncher", rv.main_class
        assert rv.client_version_id == "1.20.4"


def test_inherits_chain_and_libraries(tmp_path=None):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        r = VersionResolver(Path(d))
        _write(r, "base", {"id": "base", "mainClass": "A",
                             "libraries": [{"name": "com.example:base:1.0"}]})
        _write(r, "child", {"id": "child", "inheritsFrom": "base", "mainClass": "B",
                            "libraries": [{"name": "com.example:child:1.0"}]})
        rv = r.resolve("child")
        assert rv.main_class == "B"
        names = [lib.name for lib in rv.libraries]
        assert "com.example:child:1.0" in names
        assert "com.example:base:1.0" in names


def test_new_arguments_merged():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        r = VersionResolver(Path(d))
        _write(r, "base", {"id": "base", "arguments": {"game": ["--base"], "jvm": ["-Dbase"]}})
        _write(r, "child", {"id": "child", "inheritsFrom": "base",
                            "arguments": {"game": ["--child"]}})
        rv = r.resolve("child")
        assert "--base" in rv.game_args and "--child" in rv.game_args
        assert "-Dbase" in rv.jvm_args


def test_legacy_minecraft_arguments():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        r = VersionResolver(Path(d))
        _write(r, "1.8", {"id": "1.8", "minecraftArguments": "--width ${resolution_width}"})
        rv = r.resolve("1.8")
        assert rv.minecraft_args == "--width ${resolution_width}"
        assert rv.uses_new_arguments is False
