"""Installers must use staging, even when the selected root is F:/.minecraft."""
import json
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.install.forge import install_forge


def test_forge_uses_staging_preserves_existing_profiles():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = Config(root / "settings.json")
        cfg.set("game_dir", str(root / ".minecraft"))
        repo = GameRepository(cfg)
        base = repo.version_dir("1.20.4")
        base.mkdir(parents=True)
        (base / "1.20.4.json").write_text('{"id":"1.20.4"}', encoding="utf-8")
        (base / "1.20.4.jar").write_bytes(b"base")
        marker = repo.game_dir / "launcher_profiles.json"
        marker.write_bytes(b'{"profiles":{"user":"keep"}}')
        installer_path = repo.game_dir / ".onion" / "cache" / "installers" / "forge-1.20.4-test-installer.jar"
        installer_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(installer_path, "w") as archive:
            archive.writestr("version.json", '{"libraries":[]}')
        def installer(command, **kwargs):
            stage = Path(command[-1])
            assert stage != repo.game_dir
            assert json.loads((stage / "launcher_profiles.json").read_text()) == {}
            target = stage / "versions" / "1.20.4-forge-test"
            target.mkdir()
            (target / "1.20.4-forge-test.json").write_text('{"id":"1.20.4-forge-test"}')
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        with patch.object(repo, "install"), patch.object(repo.downloader, "download_one"), \
             patch("launcher.install.forge.subprocess.run", side_effect=installer):
            result = install_forge(repo, "1.20.4", version="1.20.4-test", java_path="java")
        assert result == "1.20.4-forge-test"
        assert marker.read_bytes() == b'{"profiles":{"user":"keep"}}'
        assert (repo.version_dir(result) / f"{result}.json").is_file()
