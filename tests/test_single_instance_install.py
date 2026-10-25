"""One new-install request publishes one self-contained instance, including retries."""
import json,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.install.instance import install_instance,next_instance_id
from launcher.download import DownloadCancelled,DownloadError
from tests.test_components import client,write,profile


def repository(base):
    config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'));return GameRepository(config)


def install_runtime(repo,vid,*args,**kwargs):
    if not repo.resolver.json_path(vid).exists():
        write(repo,vid,dict(mainClass='net.minecraft.client.main.Main',onionGameVersion='26.3',arguments=dict(game=['--demo'])),True)
    return repo.resolver.resolve(vid)


def loader(repo,game,version,kind,stage):
    install_runtime(repo,game);ident=kind+'-loader-'+version+'-'+game
    write(repo,ident,profile(version,kind)|dict(inheritsFrom=game));return ident


def test_new_fabric_quilt_and_vanilla_publish_only_one_directory():
    for kind in ('vanilla','fabric','quilt'):
        with tempfile.TemporaryDirectory() as tmp:
            repo=repository(Path(tmp));vid='26.3-'+kind
            with patch.object(GameRepository,'install',install_runtime),patch('launcher.install.fabric.install_loader',loader):
                assert install_instance(repo,'26.3',kind,'0.19.5',vid,'fixture-request')==vid
            assert repo.list_installed()==[vid]
            assert sorted(p.name for p in repo.versions_dir.iterdir())==[vid]
            raw=repo.resolver.load_raw(vid);assert raw['id']==vid and 'inheritsFrom' not in raw and 'jar' not in raw
            assert repo.client_jar_path(repo.resolver.resolve(vid)).read_bytes()==client()
            assert not list((repo.game_dir/'.onion/install').iterdir())
            if kind!='vanilla':assert any(kind+'-loader' in lib['name'] for lib in raw['libraries'])


def test_existing_game_and_instances_are_not_hidden_or_modified():
    with tempfile.TemporaryDirectory() as tmp:
        repo=repository(Path(tmp));write(repo,'26.3',dict(mainClass='net.minecraft.client.main.Main'),True)
        write(repo,'existing',dict(inheritsFrom='26.3'));before={p:p.read_bytes() for p in repo.versions_dir.rglob('*') if p.is_file()}
        with patch.object(GameRepository,'install',install_runtime),patch('launcher.install.fabric.install_loader',loader):
            install_instance(repo,'26.3','fabric','0.19.5','new-fabric','request')
        assert repo.list_installed()==['26.3','existing','new-fabric']
        assert all(p.read_bytes()==raw for p,raw in before.items())


def test_failed_or_cancelled_install_publishes_no_instances():
    for cancelled in (False,True):
        with tempfile.TemporaryDirectory() as tmp:
            repo=repository(Path(tmp));event=threading.Event()
            def broken(*args):
                loader(*args)
                if cancelled:event.set();return 'fabric-loader-0.19.5-26.3'
                raise DownloadError('fixture network failure')
            with patch.object(GameRepository,'install',install_runtime),patch('launcher.install.fabric.install_loader',broken):
                try:install_instance(repo,'26.3','fabric','0.19.5','target','request',cancel=event)
                except (DownloadError,DownloadCancelled):pass
                else:raise AssertionError('Failed installation published')
            assert repo.list_installed()==[]
            assert not list((repo.game_dir/'.onion/install').iterdir())


def test_retry_reuses_same_committed_target_and_other_request_cannot_overwrite():
    with tempfile.TemporaryDirectory() as tmp:
        repo=repository(Path(tmp))
        with patch.object(GameRepository,'install',install_runtime),patch('launcher.install.fabric.install_loader',loader):
            install_instance(repo,'26.3','fabric','0.19.5','target','same-request')
            install_instance(repo,'26.3','fabric','0.19.5','target','same-request')
            try:install_instance(repo,'26.3','fabric','0.19.5','target','different-request')
            except FileExistsError:pass
            else:raise AssertionError('Existing instance overwritten')
        assert repo.list_installed()==['target'] and next_instance_id(repo,'target')=='target-2'


def test_forge_install_intermediate_versions_also_stay_in_staging():
    with tempfile.TemporaryDirectory() as tmp:
        repo=repository(Path(tmp))
        def forge(repo,game,kind,version,*args):
            install_runtime(repo,game);ident='forge-'+version
            write(repo,ident,dict(inheritsFrom=game,mainClass='Forge',libraries=[dict(name='net.minecraftforge:forge:'+version)]));return ident
        with patch.object(GameRepository,'install',install_runtime),patch('launcher.install.forge.install_forge',forge):
            install_instance(repo,'26.3','forge','26.3-1','target','request')
        assert repo.list_installed()==['target'] and repo.resolver.resolve('target').main_class=='Forge'
