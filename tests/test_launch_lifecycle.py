"""Exercise real process/log/lock handling with a console-free Python child, never Minecraft."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from launcher.config import Config
from launcher.repository import GameRepository
from launcher.launch import launch, Account, LaunchSettings


def make_repo(root):
    config = Config(root / "settings.json")
    config.set("game_dir", str(root / "minecraft"))
    repo = GameRepository(config)
    target = repo.version_dir("child")
    target.mkdir(parents=True)
    (target / "child.json").write_text('{"id":"child","mainClass":"Main"}')
    return repo, repo.resolver.resolve("child")


def test_process_logs_exit_code_and_instance_lock_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        repo, version = make_repo(Path(d))
        ready, exited = threading.Event(), threading.Event()
        logs, exits = [], []

        def on_log(line, error):
            logs.append((line, error))
            if line == "READY":
                ready.set()

        def on_exit(code):
            exits.append(code)
            exited.set()

        script = (
            "import json,os,pathlib,sys,time; "
            "print(json.dumps({'instance':os.environ['INST_NAME'],'cwd':os.getcwd()}),flush=True); "
            "print('READY',flush=True); "
            "deadline=time.monotonic()+10\n"
            "while not pathlib.Path('finish-test').exists() and time.monotonic()<deadline: time.sleep(.02)\n"
            "print('last-error',file=sys.stderr,flush=True)\n"
            "sys.exit(7)\n"
        )
        command = [sys.executable, "-u", "-c", script]
        proc = None
        try:
            with patch("launcher.launch.build_command", return_value=command):
                proc = launch(repo, version, Account("Tester", "0" * 32), LaunchSettings(), sys.executable,
                              on_log=on_log, on_exit=on_exit)
                assert ready.wait(8), logs
                lock = repo.version_dir(version.id) / ".instance.lock"
                assert lock.read_text() == str(proc.proc.pid)
                try:
                    launch(repo, version, Account("Tester", "0" * 32), LaunchSettings(), sys.executable)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("duplicate instance was launched")
                (repo.run_dir(version.id) / "finish-test").write_text("finish")
                assert exited.wait(8), logs
            assert exits == [7]
            assert ("last-error", True) in logs
            metadata = json.loads(next(line for line, error in logs if line.startswith("{")))
            assert metadata["instance"] == version.id
            assert Path(metadata["cwd"]) == repo.run_dir(version.id)
            assert not lock.exists()
        finally:
            if proc is not None and proc.proc.poll() is None:
                proc.stop()
                proc.proc.wait(timeout=10)
                exited.wait(5)


def test_failed_process_creation_releases_lock():
    with tempfile.TemporaryDirectory() as d:
        repo, version = make_repo(Path(d))
        missing = str(Path(d) / "missing-java.exe")
        with patch("launcher.launch.build_command", return_value=[missing]):
            try:
                launch(repo, version, Account("Tester", "0" * 32), LaunchSettings(), missing)
            except OSError:
                pass
            else:
                raise AssertionError("nonexistent executable was launched")
        assert not (repo.version_dir(version.id) / ".instance.lock").exists()
