import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.config import Config
from launcher.repository import GameRepository
from launcher.safety import child, recycle, restore_recycled, write_text
from launcher.saves import backup, restore


def repository(root):
    cfg = Config(root / "settings.json")
    cfg.set("game_dir", str(root / "minecraft"))
    return GameRepository(cfg)


def test_paths_reject_traversal_and_sibling_prefix():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for relative in ("../minecraft-other/file", "a/../../escape", "F:/escape", "x:stream", "CON", "a\\..\\escape"):
            try:
                child(root / "minecraft", relative)
            except (ValueError, PermissionError):
                pass
            else:
                raise AssertionError(relative)


def test_instance_create_recycle_restore_and_dependency_guard():
    with tempfile.TemporaryDirectory() as d:
        repo = repository(Path(d))
        base = repo.version_dir("base")
        base.mkdir(parents=True)
        (base / "base.json").write_text('{"id":"base","mainClass":"Main"}')
        repo.create_instance("base", "test")
        assert repo.run_dir("test") == repo.version_dir("test")
        try:
            repo.delete_version("base")
        except RuntimeError:
            pass
        else:
            raise AssertionError("dependent base removed")
        data = repo.version_dir("test") / "saves" / "keep.dat"
        data.parent.mkdir()
        data.write_bytes(b"world")
        stored = repo.delete_version("test")
        assert not repo.version_dir("test").exists()
        restored = restore_recycled(stored, repo.versions_dir)
        assert (restored / "saves" / "keep.dat").read_bytes() == b"world"


def test_recovery_refuses_overwrite():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        source = root / "mod.jar"
        source.write_bytes(b"old")
        target = recycle(source, root)
        source.write_bytes(b"new")
        try:
            restore_recycled(target, root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("overwrote replacement")
        assert source.read_bytes() == b"new"


def test_world_backup_restore_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        world = root / "saves" / "MyWorld"
        world.mkdir(parents=True)
        (world / "level.dat").write_bytes(b"nbt")
        archive = backup(world, root / "backups")
        restored = restore(archive, root / "saves")
        assert restored != world
        assert (restored / "level.dat").read_bytes() == b"nbt"


def test_local_install_is_offline_and_failed_download_is_not_success():
    with tempfile.TemporaryDirectory() as d:
        repo = repository(Path(d))
        base = repo.version_dir("base")
        base.mkdir(parents=True)
        (base / "base.json").write_text('{"id":"base","mainClass":"Main"}')
        with patch.object(repo, "fetch_manifest", side_effect=AssertionError("network")):
            assert repo.install("base").id == "base"
        from launcher.download import DownloadError, DownloadJob
        job = DownloadJob("http://invalid", repo.game_dir / "file")
        with patch.object(repo.downloader, "download_many", return_value=([], [job])):
            try:
                repo.download_jobs([job])
            except DownloadError:
                pass
            else:
                raise AssertionError("failed download reported as success")


def test_overwrite_creates_recovery_copy():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        write_text(p, "old")
        write_text(p, "new")
        assert p.read_text() == "new"
        assert next((p.parent / ".craftbridge-backups").iterdir()).read_text() == "old"


def test_existing_instance_and_boolean_overrides():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repo = repository(root)
        repo.config.set("version_isolation", False)
        (repo.version_dir("existing") / "mods").mkdir(parents=True)
        assert repo.run_dir("existing") == repo.version_dir("existing")
        from launcher.version_settings import VersionSettingsStore
        store = VersionSettingsStore(root / "version_settings.json")
        store.set("existing", {"isolate": False, "fullscreen": False})
        repo.config.set("fullscreen", True)
        assert repo.run_dir("existing") == repo.game_dir
        assert store.resolve("existing", repo.config)["fullscreen"] is False


def test_modpack_sibling_escape_blocked():
    from launcher.modpack import _safe_extract
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        archive = root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("overrides/../instance-other/escaped", "bad")
        with zipfile.ZipFile(archive) as z:
            assert _safe_extract(z, "overrides", root / "instance") == 0
        assert not (root / "instance-other").exists()


def test_alias_uses_patched_parent_jar():
    with tempfile.TemporaryDirectory() as d:
        repo = repository(Path(d))
        base = repo.version_dir("base")
        base.mkdir(parents=True)
        (base / "base.json").write_text(json.dumps({"id": "base", "mainClass": "Main",
            "downloads": {"client": {"url": "http://invalid", "sha1": "0" * 40}}}))
        (base / "base.jar").write_bytes(b"vanilla")
        patched = repo.version_dir("patched")
        patched.mkdir()
        (patched / "patched.json").write_text('{"id":"patched","inheritsFrom":"base"}')
        (patched / "patched.jar").write_bytes(b"patched")
        repo.create_instance("patched", "alias")
        rv = repo.resolver.resolve("alias")
        assert repo.client_jar_path(rv) == patched / "patched.jar"
        with patch.object(repo.downloader, "download_one", side_effect=AssertionError("overwrite")):
            repo._ensure_client(rv)


def test_installed_loader_coordinates_survive_export():
    from launcher.modpack import _detect_loader, export_mrpack
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repo = repository(root)
        base = repo.version_dir("base")
        base.mkdir(parents=True)
        (base / "base.json").write_text(json.dumps({"id": "base", "mainClass": "Main",
            "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.14"}]}))
        repo.create_instance("base", "CustomName")
        assert _detect_loader(repo, "CustomName") == ("fabric", "0.16.14")
        archive = export_mrpack(repo, "CustomName", root / "pack.mrpack")
        with zipfile.ZipFile(archive) as z:
            index = json.loads(z.read("modrinth.index.json"))
        assert index["dependencies"]["fabric-loader"] == "0.16.14"


def test_running_instance_cannot_be_removed():
    import os
    with tempfile.TemporaryDirectory() as d:
        repo = repository(Path(d))
        target = repo.version_dir("running")
        target.mkdir(parents=True)
        (target / "running.json").write_text('{"id":"running"}')
        (target / ".instance.lock").write_text(str(os.getpid()))
        try:
            repo.delete_version("running")
        except RuntimeError:
            pass
        else:
            raise AssertionError("removed live instance")
        assert target.is_dir()


def test_cancel_propagates_to_download_workers():
    import threading
    from launcher.download import Downloader, DownloadJob
    with tempfile.TemporaryDirectory() as d:
        event = threading.Event()
        event.set()
        dl = Downloader(retries=1)
        target = Path(d) / "not-written"
        with dl.cancellable(event):
            _ok, failed = dl.download_many([DownloadJob("http://127.0.0.1:1/never", target)])
        assert len(failed) == 1
        assert not target.exists()


def test_account_authlib_roundtrip_and_microsoft_refresh():
    from launcher.accounts import AccountStore, AccountRecord
    from launcher.auth.authlib import authenticate
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "accounts.json"
        store = AccountStore(path)
        with patch("launcher.auth.authlib._post_json", return_value={"accessToken": "test-token",
                "selectedProfile": {"id": "a" * 32, "name": "Tester"}}):
            data = authenticate("https://example.invalid", "test", "not-stored")
        store.add(AccountRecord(type="authlib", **data))
        loaded = AccountStore(path).current()
        assert loaded.authlib_url == "https://example.invalid"
        assert loaded.user_type == "mojang"
        assert "not-stored" not in path.read_text()
        account = AccountRecord(type="microsoft", username="Tester", uuid="b" * 32,
                                client_id="app", refresh_token="old", expires_at=1)
        with patch("launcher.auth.microsoft.refresh_minecraft", return_value={
                "access_token": "new", "refresh_token": "rotated", "expires_at": 9999999999}):
            assert store.ensure_fresh(account).access_token == "new"
        assert AccountStore(path).get(account.uuid).refresh_token == "rotated"


def test_mirror_missing_artifact_falls_back_without_losing_old_file():
    from tests.harness import FakeServer
    from launcher.download import Downloader, DownloadJob
    import hashlib
    server = FakeServer({"/official": b"new-data"}).start()
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "library.jar"
            path.write_bytes(b"old-data")
            job = DownloadJob(server.url("/missing"), path,
                              sha1=hashlib.sha1(b"new-data").hexdigest(),
                              fallback_urls=(server.url("/official"),))
            Downloader(retries=1).download_one(job)
            assert path.read_bytes() == b"new-data"
            assert next((path.parent / ".craftbridge-backups").iterdir()).read_bytes() == b"old-data"
    finally:
        server.stop()


def test_asset_and_library_metadata_cannot_escape_subdirectories():
    from launcher.assets import AssetObject
    from launcher.libraries import Library
    with tempfile.TemporaryDirectory() as d:
        for action in (lambda: AssetObject("x", "../../versions/x", 1).object_path(),
                       lambda: Library.from_json({"name":"a:b:1", "downloads":{"artifact":{
                           "path":"../versions/existing.json"}}}).artifact_file(Path(d) / "libraries")):
            try:
                action()
            except (ValueError, PermissionError):
                pass
            else:
                raise AssertionError("metadata escaped its directory")
