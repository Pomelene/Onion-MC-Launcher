import stat
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.saves import backup, restore


def test_repeated_restore_same_second_preserves_every_world():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        world = root / "saves" / "World"
        world.mkdir(parents=True)
        (world / "level.dat").write_bytes(b"original")
        archive = backup(world, root / "backups")
        with patch("launcher.saves.time.strftime", return_value="same-second"):
            first = restore(archive, root / "saves")
            (first / "level.dat").write_bytes(b"played-after-restore")
            second = restore(archive, root / "saves")
        assert len({world, first, second}) == 3
        assert (world / "level.dat").read_bytes() == b"original"
        assert (first / "level.dat").read_bytes() == b"played-after-restore"
        assert (second / "level.dat").read_bytes() == b"original"


def test_unsafe_archive_publishes_no_partial_world():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        archive = root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("World/level.dat", b"valid-looking")
            z.writestr("World/../../escaped", b"bad")
        saves = root / "saves"
        try:
            restore(archive, saves)
        except (ValueError, PermissionError):
            pass
        else:
            raise AssertionError("unsafe archive was accepted")
        assert not list(saves.iterdir())
        assert not (root / "escaped").exists()


def test_flat_legacy_backup_remains_restorable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        archive = root / "LegacyWorld.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("level.dat", b"legacy-world")
            z.writestr("region/r.0.0.mca", b"region")
        target = restore(archive, root / "saves")
        assert target.name == "LegacyWorld"
        assert (target / "level.dat").read_bytes() == b"legacy-world"
        assert (target / "region/r.0.0.mca").read_bytes() == b"region"


def test_backup_cannot_include_itself():
    with tempfile.TemporaryDirectory() as d:
        world = Path(d) / "World"
        world.mkdir()
        (world / "level.dat").write_bytes(b"world")
        try:
            backup(world, world / "backups")
        except ValueError:
            pass
        else:
            raise AssertionError("recursive backup was accepted")
        assert not (world / "backups").exists()


def test_symlink_in_archive_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        archive = root / "link.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("World/level.dat", b"nbt")
            link = zipfile.ZipInfo("World/linked")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, "../../outside")
        try:
            restore(archive, root / "saves")
        except ValueError:
            pass
        else:
            raise AssertionError("symbolic link accepted")
        assert not list((root / "saves").iterdir())


def test_world_selection_uses_application_setter_without_tk_window():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from launcher.ui.pages.worlds import WorldsPage
    page = SimpleNamespace(version_var=Mock(), app=SimpleNamespace(set_selected_version=Mock()),
                           _reload_worlds=Mock())
    WorldsPage._choose(page, "Instance B")
    page.version_var.set.assert_called_once_with("Instance B")
    page.app.set_selected_version.assert_called_once_with("Instance B")
    page._reload_worlds.assert_called_once()
