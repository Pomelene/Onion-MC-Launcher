"""Existing-instance loader changes must not create profiles or touch game data."""
import io,json,tempfile,threading,zipfile
from pathlib import Path
from unittest.mock import patch
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.components import component_info,replace_loader
from launcher.download import DownloadError,DownloadCancelled


def client(game='26.3'):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr(zipfile.ZipInfo('version.json',date_time=(2026,1,1,0,0,0)),json.dumps(dict(id=game,java_version=25)))
    return out.getvalue()


def profile(version,kind='fabric'):
    group,artifact,main=('net.fabricmc','fabric-loader','net.fabricmc.loader.impl.launch.knot.KnotClient') if kind=='fabric' else ('org.quiltmc','quilt-loader','org.quiltmc.loader.impl.launch.knot.KnotClient')
    return dict(inheritsFrom='26.3',mainClass=main,libraries=[dict(name=f'{group}:{artifact}:{version}'),dict(name='org.ow2.asm:asm:9.9')],arguments=dict(jvm=['-Dloader.version='+version]))


def write(repo,vid,data,jar=False):
    folder=repo.version_dir(vid);folder.mkdir(parents=True,exist_ok=True);path=folder/(vid+'.json');path.write_text(json.dumps(dict(data,id=vid)),encoding='utf-8')
    if jar:path.with_suffix('.jar').write_bytes(client())
    return path


def fixture(base,inherited=False,vanilla=False):
    config=Config(base/'onionmcl.json');config.update(dict(game_dir=str(base/'game'),version_isolation=True));repo=GameRepository(config)
    base_data=dict(mainClass='net.minecraft.client.main.Main',libraries=[dict(name='example:keep:1',rules=[dict(action='allow')])],arguments=dict(game=['--username','${auth_player_name}'],jvm=[{'rules':[{'action':'allow','features':{'fixture':True}}],'value':'-Dconditional=true'}]))
    vid='26.3-Fabric-THUnion'
    if inherited:
        write(repo,'26.3',base_data,True);write(repo,'parent',profile('0.19.4')|dict(inheritsFrom='26.3'))
        write(repo,'sibling',dict(inheritsFrom='parent'));write(repo,vid,dict(inheritsFrom='parent',customField='keep me'))
    else:
        data=base_data
        if not vanilla:
            old=profile('0.19.4');data=base_data|old
            data['libraries']=old['libraries']+base_data['libraries']
            data['arguments']={'game':base_data['arguments']['game'],'jvm':base_data['arguments']['jvm']+old['arguments']['jvm']}
        data.pop('inheritsFrom',None);write(repo,vid,data,True)
    for name in ('mods/a.jar','saves/world/level.dat','config/a.json','options.txt'):
        path=repo.version_dir(vid)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('sentinel '+name).encode())
    def fetch(url):
        if url.endswith('/profile/json'):
            version=url.split('/')[-3];kind='quilt' if 'quiltmc' in url else 'fabric';return profile(version,kind)
        return [dict(loader=dict(version=v,stable=True)) for v in ('0.19.5','0.19.4','0.19.3')]
    repo.downloader.fetch_json=fetch
    return repo,vid


def data_snapshot(repo,vid):
    folder=repo.version_dir(vid)
    return {str(path.relative_to(folder)):path.read_bytes() for path in folder.rglob('*') if path.is_file() and path.name!=vid+'.json' and '.craftbridge-backups' not in path.parts}


def test_merged_instance_upgrade_and_downgrade_keep_id_data_and_only_new_loader():
    with tempfile.TemporaryDirectory() as tmp:
        repo,vid=fixture(Path(tmp));before=data_snapshot(repo,vid);ids=repo.list_installed()
        with patch.object(repo,'_ensure_libraries') as libraries,patch.object(repo,'install',side_effect=AssertionError('Must not install a new instance')):
            assert replace_loader(repo,vid,'fabric','0.19.5')==vid
            assert component_info(repo,vid)==('26.3','fabric','0.19.5')
            replace_loader(repo,vid,'fabric','0.19.3')
            assert component_info(repo,vid)==('26.3','fabric','0.19.3')
            assert len(libraries.call_args.args[0].libraries)==2
        assert repo.list_installed()==ids and data_snapshot(repo,vid)==before
        raw=repo.resolver.load_raw(vid);assert raw['id']==vid and 'inheritsFrom' not in raw
        assert [lib['name'] for lib in raw['libraries']].count('net.fabricmc:fabric-loader:0.19.3')==1
        assert not any('0.19.4' in lib['name'] or '0.19.5' in lib['name'] for lib in raw['libraries'])
        assert raw['arguments']['game']==['--username','${auth_player_name}']
        assert '-Dconditional=true' in repo.resolver.resolve(vid,{'fixture':True}).jvm_args
        assert '-Dloader.version=0.19.5' not in raw['arguments']['jvm']


def test_inherited_instance_is_detached_without_modifying_parent_or_sibling():
    with tempfile.TemporaryDirectory() as tmp:
        repo,vid=fixture(Path(tmp),inherited=True);ids=repo.list_installed();before=data_snapshot(repo,vid)
        untouched={other:repo.resolver.json_path(other).read_bytes() for other in ids if other!=vid}
        with patch.object(repo,'_ensure_libraries'):replace_loader(repo,vid,'fabric','0.19.5')
        assert repo.list_installed()==ids and data_snapshot(repo,vid)==before
        assert all(repo.resolver.json_path(other).read_bytes()==raw for other,raw in untouched.items())
        assert component_info(repo,'sibling')[2]=='0.19.4' and component_info(repo,vid)[2]=='0.19.5'
        assert repo.client_jar_path(repo.resolver.resolve(vid))==repo.version_dir('26.3')/'26.3.jar'
        assert repo.resolver.load_raw(vid)['customField']=='keep me'


def test_vanilla_can_add_fabric_or_quilt_in_place():
    for kind in ('fabric','quilt'):
        with tempfile.TemporaryDirectory() as tmp:
            repo,vid=fixture(Path(tmp),vanilla=True);before=data_snapshot(repo,vid)
            with patch.object(repo,'_ensure_libraries'):replace_loader(repo,vid,kind,'0.19.5')
            assert component_info(repo,vid)==('26.3',kind,'0.19.5') and repo.list_installed()==[vid]
            assert data_snapshot(repo,vid)==before


def test_failure_cancel_or_profile_change_never_replaces_active_json():
    for case in ('download','cancel','changed','wrong-profile','wrong-game'):
        with tempfile.TemporaryDirectory() as tmp:
            repo,vid=fixture(Path(tmp));path=repo.resolver.json_path(vid);before=path.read_bytes();cancel=threading.Event()
            def prepare(*args):
                if case=='download':raise DownloadError('fixture network failure')
                if case=='cancel':cancel.set()
                if case=='changed':path.write_bytes(before+b' ')
            if case=='wrong-profile':repo.downloader.fetch_json=lambda url: profile('wrong') if url.endswith('/profile/json') else [dict(loader=dict(version='0.19.5'))]
            with patch.object(repo,'_ensure_libraries',side_effect=prepare):
                try:replace_loader(repo,vid,'fabric','0.19.5',cancel=cancel,expected_game='1.21' if case=='wrong-game' else None)
                except (DownloadError,ValueError,RuntimeError):pass
                else:raise AssertionError('Invalid update accepted: '+case)
            assert path.read_bytes()==before+(b' ' if case=='changed' else b'') and repo.list_installed()==[vid]


def test_shared_parent_and_incompatible_components_are_not_silently_changed():
    with tempfile.TemporaryDirectory() as tmp:
        repo,vid=fixture(Path(tmp));write(repo,'dependent',dict(inheritsFrom=vid));before=repo.resolver.json_path(vid).read_bytes()
        with patch.object(repo,'_ensure_libraries') as download:
            try:replace_loader(repo,vid,'fabric','0.19.5')
            except ValueError:pass
            else:raise AssertionError('Shared parent was modified')
            download.assert_not_called()
        assert repo.resolver.json_path(vid).read_bytes()==before
        repo.resolver.json_path('dependent').unlink()
        raw=repo.resolver.load_raw(vid);raw['libraries'].insert(0,dict(name='net.minecraftforge:forge:26.3-1'));write(repo,vid,raw)
        with patch.object(repo,'_ensure_libraries'):
            try:replace_loader(repo,vid,'fabric','0.19.5')
            except ValueError:pass
            else:raise AssertionError('Incompatible loader replaced')
