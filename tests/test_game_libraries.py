"""Same-named instances across roots must never share overrides or metadata."""
import tempfile
import json
from pathlib import Path
from launcher.config import Config
from launcher.instance import InstanceStore
from launcher.version_settings import VersionSettingsStore
from launcher.game_libraries import GameLibraries
from launcher.repository import GameRepository
from launcher.storage import read_section,directory_key


def test_legacy_metadata_belongs_only_to_original_library():
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);path=base/'onionmcl.json';a=base/'a';b=base/'b';a.mkdir();b.mkdir()
        config=Config(path);config.update({'game_dir':str(a),'selected_version':'same'})
        InstanceStore(path).update('same',name='原来的名称',group='红石')
        VersionSettingsStore(path).set('same',{'max_memory':6144,'isolate':False})
        libraries=GameLibraries(config);libraries.ensure_current();libraries.add(b)
        legacy=config.get('library_legacy_root')
        assert InstanceStore(path,a,legacy).display_name('same')=='原来的名称'
        assert VersionSettingsStore(path,a,legacy).get('same')['max_memory']==6144
        assert InstanceStore(path,b,legacy).display_name('same')=='same'
        assert VersionSettingsStore(path,b,legacy).get('same')=={}
        VersionSettingsStore(path,a,legacy).clear('same')
        assert VersionSettingsStore(path,a,legacy).get('same')=={},'Empty overrides must not resurrect flat legacy data'
        assert read_section(path,'version_settings')['same']['max_memory']==6144,'Original flat record must remain recoverable'


def test_scoped_writes_preserve_other_folders_and_route_game_files():
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);path=base/'onionmcl.json';a=base/'a';b=base/'b';a.mkdir();b.mkdir()
        config=Config(path);config.set('game_dir',str(a));GameLibraries(config).ensure_current()
        aa=InstanceStore(path,a,a);bb=InstanceStore(path,b,a)
        va=VersionSettingsStore(path,a,a);vb=VersionSettingsStore(path,b,a)
        aa.update('same',name='A 实例');bb.update('same',name='B 实例');aa.record_launch('same');bb.add_play_time('same',30)
        va.set('same',{'max_memory':2048,'isolate':False});vb.set('same',{'max_memory':8192,'isolate':True})
        assert InstanceStore(path,a,a).display_name('same')=='A 实例'
        assert InstanceStore(path,b,a).display_name('same')=='B 实例'
        assert InstanceStore(path,a,a).get('same').play_seconds==0
        ra=GameRepository(config);config.set('game_dir',str(b));rb=GameRepository(config)
        assert ra.run_dir('same')==a,'Repository keeps its own root even after global selection changes'
        assert rb.run_dir('same')==b/'versions/same'
        assert VersionSettingsStore(path,a,a).get('same')['max_memory']==2048
        assert VersionSettingsStore(path,b,a).get('same')['max_memory']==8192


def test_library_catalog_remembers_selection_and_never_deletes_files():
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);path=base/'onionmcl.json';a=base/'a';b=base/'b';a.mkdir();b.mkdir()
        marker=b/'keep.txt';marker.write_text('keep');config=Config(path);config.set('game_dir',str(a))
        libraries=GameLibraries(config);libraries.ensure_current();libraries.remember('a-version');libraries.add(b)
        libraries.add(b/'../b');assert len(libraries.entries())==2
        config.set('game_dir',str(b));libraries.remember('b-version');libraries.rename(b,'生存')
        config.set('game_dir',str(a));libraries.remember('a-version')
        restored=GameLibraries(Config(path));assert restored.selection(a)=='a-version' and restored.selection(b)=='b-version'
        assert next(item for item in restored.entries() if directory_key(item['path'])==directory_key(b))['name']=='生存'
        restored.remove(b);assert marker.read_text()=='keep' and len(restored.entries())==1
        try:restored.remove(a)
        except ValueError:pass
        else:raise AssertionError('Active game folder cannot be removed')
        before=path.read_bytes()
        try:restored.add(base/'missing')
        except ValueError:pass
        else:raise AssertionError('Unavailable folder must not become active')
        assert before==path.read_bytes()


def test_v1_document_upgrades_without_losing_original_records():
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);path=base/'onionmcl.json';root=base/'game';root.mkdir()
        document={'format_version':1,'settings':{'game_dir':str(root)},'accounts':{},
                  'instances':{'same':{'name':'原名称'}},'version_settings':{'same':{'max_memory':6144}}}
        path.write_text(json.dumps(document),encoding='utf-8')
        original=path.read_bytes()
        config=Config(path);GameLibraries(config).ensure_current()
        upgraded=json.loads(path.read_text(encoding='utf-8'))
        assert upgraded['format_version']==2
        for section in ('accounts','instances','version_settings'):assert upgraded[section]==document[section]
        assert InstanceStore(path,root,root).display_name('same')=='原名称'
        backups=list((base/'.onion/backups').glob('onionmcl-format1-*.json'))
        assert len(backups)==1 and backups[0].read_bytes()==original


def test_simultaneous_directory_writers_preserve_each_namespace():
    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory() as folder:
        base=Path(folder);path=base/'onionmcl.json'
        Config(path).set('game_dir',str(base/'a'))
        def write(root):
            store=VersionSettingsStore(path,root)
            for value in range(10):store.set('same',{'max_memory':1024+value})
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(write,(base/'a',base/'b')))
        for root in (base/'a',base/'b'):assert VersionSettingsStore(path,root).get('same')['max_memory']==1033
