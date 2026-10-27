import json
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.config import Config
from launcher.repository import GameRepository
from launcher.modpack import export_mrpack
from launcher.file_library import export_pictures,remove_entries
from launcher.safety import restore_recycled


def test_mrpack_selection_metadata_and_cancel():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'))
        repo=GameRepository(config);instance=repo.version_dir('1.20.4');instance.mkdir(parents=True)
        (instance/'1.20.4.json').write_text(json.dumps({'id':'1.20.4','type':'release'}))
        (instance/'.isolate').write_text('1');(instance/'mods').mkdir();(instance/'mods'/'test.jar').write_bytes(b'mod')
        (instance/'saves'/'world').mkdir(parents=True);(instance/'saves'/'world'/'level.dat').write_bytes(b'world')
        output=root/'export.mrpack'
        export_mrpack(repo,'1.20.4',output,'Test',pack_version='2.1',selected=['mods'])
        with zipfile.ZipFile(output) as archive:
            manifest=json.loads(archive.read('modrinth.index.json'))
            assert manifest['name']=='Test' and manifest['versionId']=='2.1' and manifest['files']==[]
            assert archive.read('overrides/mods/test.jar')==b'mod'
            assert not any(name.startswith('overrides/saves/') for name in archive.namelist())
        before=output.read_bytes();cancel=threading.Event();cancel.set()
        try:export_mrpack(repo,'1.20.4',output,selected=['mods'],cancel=cancel)
        except Exception:pass
        else:raise AssertionError('Cancellation was ignored')
        assert output.read_bytes()==before and not list(root.glob('*.tmp'))


def test_bulk_screenshot_export_conflict_and_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);folder=root/'screenshots';folder.mkdir();destination=root/'export';destination.mkdir()
        first=folder/'one.png';second=folder/'two.png';first.write_bytes(b'1');second.write_bytes(b'2')
        assert export_pictures(folder,[first,second],destination)==2
        try:export_pictures(folder,[first,second],destination)
        except FileExistsError:pass
        else:raise AssertionError('Existing screenshots overwritten')
        assert (destination/'one.png').read_bytes()==b'1'
        moved=remove_entries(folder,[first,second]);assert not first.exists() and not second.exists()
        for saved,parent in moved:restore_recycled(saved,parent)
        assert first.read_bytes()==b'1' and second.read_bytes()==b'2'


def test_import_multimc_common_profile_publishes_one_instance():
    from launcher.modpack import import_modpack,read_modpack_info
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'))
        repo=GameRepository(config);archive=root/'pack.zip'
        components=[{'uid':'net.minecraft','version':'1.20.4'},{'uid':'net.fabricmc.fabric-loader','version':'0.15.0'}, {'uid':'org.lwjgl3','version':'3.3.1'}]
        with zipfile.ZipFile(archive,'w') as out:
            out.writestr('Pack/instance.cfg','name=Example Pack\n')
            out.writestr('Pack/mmc-pack.json',json.dumps({'components':components}))
            out.writestr('Pack/.minecraft/mods/sample.jar',b'mod')
            out.writestr('Pack/.minecraft/saves/world/level.dat',b'world')
        info=read_modpack_info(archive);assert (info.kind,info.loader,info.loader_version)==('multimc','fabric','0.15.0')
        def install(self,vid,*args):
            if vid=='1.20.4':
                folder=self.version_dir(vid);folder.mkdir(parents=True,exist_ok=True)
                (folder/f'{vid}.json').write_text(json.dumps({'id':vid,'mainClass':'Main','downloads':{'client':{'url':'https://example.invalid/client.jar'}}}))
                (folder/f'{vid}.jar').write_bytes(b'client')
            return self.resolver.resolve(vid)
        def loader(self,game,version,kind,stage):
            vid=f'{kind}-loader-{version}-{game}';folder=self.version_dir(vid);folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{vid}.json').write_text(json.dumps({'id':vid,'inheritsFrom':game,'mainClass':'Fabric','libraries':[{'name':'net.fabricmc:fabric-loader:'+version}]}))
            return vid
        with patch.object(GameRepository,'install',install),patch('launcher.install.fabric.install_loader',loader):
            vid=import_modpack(repo,archive)
        assert repo.list_installed()==[vid]
        assert (repo.version_dir(vid)/'mods/sample.jar').read_bytes()==b'mod'
        assert (repo.version_dir(vid)/'saves/world/level.dat').read_bytes()==b'world'
        assert repo.resolver.resolve(vid).game_version=='1.20.4'
        assert (repo.version_dir(vid)/'.isolate').is_file()


def test_multimc_rejects_unhandled_component_before_install():
    from launcher.modpack import read_modpack_info
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'pack.zip'
        with zipfile.ZipFile(archive,'w') as out:
            out.writestr('mmc-pack.json',json.dumps({'components':[{'uid':'net.minecraft','version':'1.20.4'},{'uid':'custom.component','version':'1'}]}))
        try:read_modpack_info(archive)
        except Exception as error:assert 'custom.component' in str(error)
        else:raise AssertionError('unknown component silently ignored')


def test_legacy_fabric_install_publishes_one_instance():
    from launcher.install.instance import install_instance
    from launcher.modpack import _detect_loader
    from launcher.download import Downloader
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'));repo=GameRepository(config)
        requests=[]
        def fetch(self,url):
            requests.append(url)
            if url.endswith('/profile/json'):
                return {'inheritsFrom':'1.8.9','mainClass':'net.minecraft.launchwrapper.Launch',
                        'libraries':[{'name':'net.fabricmc:fabric-loader:0.16.0'}],
                        'minecraftArguments':'--tweakClass net.fabricmc.loader.launch.knot.KnotClient'}
            return [{'loader':{'version':'0.16.0','stable':True}}]
        def install(self,vid,*args):
            if vid=='1.8.9':
                folder=self.version_dir(vid);folder.mkdir(parents=True,exist_ok=True)
                (folder/f'{vid}.json').write_text(json.dumps({'id':vid,'mainClass':'Main','downloads':{'client':{'url':'https://example.invalid/client'}}}))
                (folder/f'{vid}.jar').write_bytes(b'client')
            elif vid.startswith('legacyfabric-loader-'):
                folder=self.version_dir('1.8.9');folder.mkdir(parents=True,exist_ok=True)
                (folder/'1.8.9.json').write_text(json.dumps({'id':'1.8.9','mainClass':'Main','downloads':{'client':{'url':'https://example.invalid/client'}}}))
                (folder/'1.8.9.jar').write_bytes(b'client')
            return self.resolver.resolve(vid)
        with patch.object(Downloader,'fetch_json',fetch),patch.object(GameRepository,'install',install):
            vid=install_instance(repo,'1.8.9','legacyfabric','0.16.0','legacy-test')
        assert repo.list_installed()==['legacy-test']
        assert _detect_loader(repo,vid)==('legacyfabric','0.16.0')
        assert repo.loader_label(vid)=='Legacy Fabric'
        assert all(url.startswith('https://meta.legacyfabric.net/v2/') for url in requests)
        try:export_mrpack(repo,vid,root/'legacy.mrpack')
        except ValueError as error:assert 'Legacy Fabric' in str(error)
        else:raise AssertionError('unrepresentable dependency exported')
