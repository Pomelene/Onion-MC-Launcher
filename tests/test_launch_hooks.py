import os,shlex,subprocess,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
from launcher.config import Config
from launcher.launch import Account,LaunchSettings,launch
from launcher.repository import GameRepository
from launcher.version import ResolvedVersion


def command(*args):return subprocess.list2cmdline(args) if os.name=='nt' else shlex.join(args)


def fixture(root):
    config=Config(root/'settings.json');config.set('game_dir',str(root/'game'))
    repo=GameRepository(config);repo.version_dir('fixture').mkdir(parents=True)
    return repo,ResolvedVersion(id='fixture'),Account('test','0'*32)


def test_pre_and_post_commands_run_and_receive_instance_environment():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);repo,version,account=fixture(root);finished=threading.Event()
        before=root/'before.txt';after=root/'after.txt'
        pre=command(sys.executable,'-c',f'import os,pathlib;pathlib.Path({str(before)!r}).write_text(os.environ["INST_NAME"])')
        post=command(sys.executable,'-c',f'import os,pathlib;pathlib.Path({str(after)!r}).write_text(os.environ["INST_NAME"])')
        settings=LaunchSettings(pre_launch_command=pre,post_exit_command=post)
        with patch('launcher.launch.build_command',return_value=[sys.executable,'-c','pass']):
            process=launch(repo,version,account,settings,sys.executable,on_exit=lambda _:finished.set())
            assert finished.wait(10)
        deadline=time.monotonic()+10
        while not after.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert before.read_text()=='fixture' and after.read_text()=='fixture'
        assert not (repo.version_dir('fixture')/'.instance.lock').exists()


def test_failed_pre_command_never_launches_game_and_releases_lock():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);repo,version,account=fixture(root);game=root/'game-started'
        settings=LaunchSettings(pre_launch_command=command(sys.executable,'-c','import sys;sys.exit(7)'))
        game_command=[sys.executable,'-c',f'import pathlib;pathlib.Path({str(game)!r}).touch()']
        with patch('launcher.launch.build_command',return_value=game_command):
            try:launch(repo,version,account,settings,sys.executable)
            except RuntimeError as error:assert '7' in str(error)
            else:raise AssertionError('pre-command failure was ignored')
        assert not game.exists() and not (repo.version_dir('fixture')/'.instance.lock').exists()
