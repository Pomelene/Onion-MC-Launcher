import json
import os
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.config import Config
from launcher.datapacks import import_zip,scan,remove
from launcher.safety import restore_recycled
from launcher.version_settings import VersionSettingsStore


def test_datapack_import_conflict_and_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);source=root/'pack.zip';folder=root/'world'/'datapacks'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('pack.mcmeta',json.dumps({'pack':{'pack_format':10,'description':'hello'}}))
        target=import_zip(folder,source)
        entries=scan(folder)
        assert len(entries)==1 and entries[0].description=='hello'
        try:import_zip(folder,source)
        except FileExistsError:pass
        else:raise AssertionError('existing data pack overwritten')
        assert target.exists()
        trashed=remove(folder,target);assert not target.exists()
        assert restore_recycled(trashed,folder)==target and target.exists()
        invalid=root/'invalid.zip'
        with zipfile.ZipFile(invalid,'w') as archive:archive.writestr('other.txt','x')
        try:import_zip(folder,invalid)
        except ValueError:pass
        else:raise AssertionError('invalid pack accepted')
        assert not (folder/'invalid.zip').exists()


def test_priority_global_and_instance_inheritance():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);config=Config(root/'settings.json');config.set('process_priority','below')
        overrides=VersionSettingsStore(root/'version_settings.json')
        assert overrides.resolve('first',config)['process_priority']=='below'
        overrides.set('first',{'process_priority':'above'})
        assert overrides.resolve('first',config)['process_priority']=='above'
        assert overrides.resolve('second',config)['process_priority']=='below'
        config.set('process_priority','invalid');assert config.get('process_priority')=='normal'


def test_priority_reaches_game_process_creation():
    from launcher.repository import GameRepository
    from launcher.launch import Account,LaunchSettings,launch
    from launcher.version import ResolvedVersion
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'))
        repo=GameRepository(config);repo.version_dir('fixture').mkdir(parents=True)
        captured=[];original=subprocess.Popen;exited=threading.Event()
        def spawn(*args,**kwargs):
            captured.append(kwargs['creationflags']);return original(*args,**kwargs)
        with patch('launcher.launch.build_command',return_value=[sys.executable,'-c','print("test")']),patch('launcher.launch.subprocess.Popen',side_effect=spawn):
            process=launch(repo,ResolvedVersion(id='fixture'),Account('test','0'*32),LaunchSettings(process_priority='below'),sys.executable,on_exit=lambda _:exited.set())
            process.proc.wait(timeout=10)
            assert exited.wait(10)
        assert len(captured)==1
        if os.name=='nt':assert captured[0] & 0x00004000
        else:assert captured[0]==0
