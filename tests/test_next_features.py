"""No-network safety regression for dependency plans and local feature metadata."""
import hashlib,io,json,tempfile,threading,zipfile
from pathlib import Path
from unittest.mock import patch
from launcher.mod_audit import audit,inspect_jar,matches
from launcher.mod_plan import build_plan,apply_plan,undo_last,recover_interrupted,updates,snapshot
from launcher.download import DownloadCancelled
from launcher.config import Config
from launcher.repository import GameRepository
from launcher.instance import InstanceStore,normalize_tags
from launcher.skins import SkinLibrary
from launcher.task_history import TaskHistory


def jar(key,version='1.0',depends=None,extra=None):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('fabric.mod.json',json.dumps(dict(id=key,name=key,version=version,depends=depends or {},**(extra or {}))))
    return out.getvalue()


def release(key,data,version='1.0',deps=None,date='2026-10-25T00:00:00Z'):
    return dict(id=key+'-'+version,project_id=key,version_number=version,name=key,game_versions=['1.21.1'],loaders=['fabric'],version_type='release',date_published=date,dependencies=deps or [],
                files=[dict(filename=key+'-'+version+'.jar',url='https://cdn.modrinth.com/data/'+key+'/'+version+'.jar',size=len(data),primary=True,hashes=dict(sha1=hashlib.sha1(data).hexdigest()))])


class Catalog:
    def __init__(self,versions,blobs):self.versions=versions;self.blobs=blobs;self.calls=[];self.fail=False
    def fetch_json(self,url):
        self.calls.append(url)
        if '/version_file/' in url:
            digest=url.split('/version_file/')[1].split('?')[0]
            return next(v for v in self.versions if v['files'][0]['hashes']['sha1']==digest)
        if '/project/' in url:
            key=url.split('/project/')[1].split('/')[0];return [v for v in self.versions if v['project_id']==key]
        key=url.rsplit('/',1)[-1];return next(v for v in self.versions if v['id']==key)
    def download_one(self,job):
        if self.fail:raise OSError('fixture download failure')
        job.path.parent.mkdir(parents=True,exist_ok=True);job.path.write_bytes(self.blobs[job.url])


def fixture(base,versions=None,blobs=None):
    config=Config(base/'onionmcl.json');config.update(dict(game_dir=str(base/'game'),version_isolation=True))
    catalog=Catalog(versions or [],blobs or {});repo=GameRepository(config,catalog)
    path=repo.versions_dir/'fixture';path.mkdir(parents=True)
    (path/'fixture.json').write_text(json.dumps(dict(id='fixture',onionGameVersion='1.21.1',mainClass='net.minecraft.client.main.Main',javaVersion=dict(majorVersion=21),libraries=[dict(name='net.fabricmc:fabric-loader:0.16.14')],arguments=dict(game=[],jvm=[]))))
    folder=repo.run_dir('fixture')/'mods';folder.mkdir(parents=True,exist_ok=True)
    return repo,folder,catalog


def test_version_predicates_and_unknown_are_conservative():
    assert matches('1.2.3','>=1.2 <2') is True
    assert matches('1.9','1.2.x') is False
    assert matches('1.2.8','1.2.*') is True
    assert matches('0.0.3','^0.0.3') is True and matches('0.0.4','^0.0.3') is False
    assert matches('1.2.9','~1.2.3') is True and matches('1.3','~1.2.3') is False
    assert matches('1.2.3','[1.0,2.0)') is True and matches('2.0','[1.0,2.0)') is False
    assert matches('1.2.3-rc.1','>=1.2.3') is False
    assert matches('custom-build','>=1.2') is None
    assert matches('2.0',['1.x','2.x']) is True


def test_audit_missing_disabled_duplicates_versions_and_aliases():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'a.jar').write_bytes(jar('a',depends={'b':'>=2','java':'>=21'}))
        (root/'b.jar.disabled').write_bytes(jar('b','2.0'))
        assert any(i.code=='missing' and i.dependency=='b' for i in audit(root,loader='fabric',java='21'))
        (root/'b.jar').write_bytes(jar('b','1.0',extra={'provides':['alias']}))
        assert any(i.code=='version' for i in audit(root,loader='fabric',java='21'))
        (root/'other.jar').write_bytes(jar('b','2.0'))
        assert any(i.code=='duplicate' for i in audit(root))


def test_nested_mods_satisfy_required_dependency():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('fabric.mod.json',json.dumps(dict(id='a',version='1.0',depends={'nested':'>=1'},jars=[dict(file='META-INF/jars/nested.jar')])))
            z.writestr('META-INF/jars/nested.jar',jar('nested'))
        (root/'a.jar').write_bytes(out.getvalue());assert not [i for i in audit(root,loader='fabric') if i.severity=='error']


def test_malformed_metadata_and_bounded_read():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'bad.jar').write_bytes(b'not a jar')
        (root/'wrong.jar').write_bytes(jar('wrong',depends=['broken']))
        assert len([i for i in audit(root) if i.code=='metadata'])==2
        with zipfile.ZipFile(root/'large.jar','w',zipfile.ZIP_DEFLATED) as z:z.writestr('fabric.mod.json',b' '*300000)
        assert any(i.code=='unsupported' and i.severity=='warning' and i.path.endswith('large.jar') for i in audit(root))


def test_forge_dependency_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        with zipfile.ZipFile(root/'forge.jar','w') as z:z.writestr('META-INF/mods.toml','[[mods]]\nmodId="sample"\nversion="1.0"\n[[dependencies.sample]]\nmodId="minecraft"\nmandatory=true\nversionRange="[1.21,1.22)"\nside="BOTH"\n')
        assert not [i for i in audit(root,'1.21.1','forge','52.0') if i.severity=='error']
        assert any(i.code=='version' for i in audit(root,'1.20.1','forge','52.0'))


def test_shared_dependency_plan_and_optional_allocation():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);dep=release('lib',jar('lib'));optional=release('optional',jar('optional'))
        deps=[dict(project_id='lib',version_id=dep['id'],dependency_type='required'),dict(project_id='optional',dependency_type='optional')]
        a=release('a',jar('a',depends={'lib':'*'}),deps=deps);b=release('b',jar('b',depends={'lib':'*'}),deps=deps)
        repo,folder,catalog=fixture(base,[a,b,dep,optional]);plan=build_plan(catalog,folder,[a,b],'1.21.1','fabric')
        assert len(plan['entries'])==3
        lib=next(v for v in plan['entries'] if v['project']=='lib');assert len(lib['reasons'])==2
        assert len(build_plan(catalog,folder,[a,b],'1.21.1','fabric',optional=True)['entries'])==4


def test_conflicting_pins_are_rejected_without_writes():
    with tempfile.TemporaryDirectory() as tmp:
        dep=release('lib',jar('lib'));other=release('lib',jar('lib','2.0'),'2.0')
        a=release('a',jar('a'),deps=[dict(project_id='lib',version_id=dep['id'],dependency_type='required')])
        b=release('b',jar('b'),deps=[dict(project_id='lib',version_id=other['id'],dependency_type='required')])
        repo,folder,catalog=fixture(Path(tmp),[a,b,dep,other])
        try:build_plan(catalog,folder,[a,b],'1.21.1','fabric');assert False
        except ValueError:pass
        assert not list(folder.iterdir())


def test_apply_and_undo_keep_original_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        old_data=jar('a');new_data=jar('a','2.0');old=release('a',old_data,date='2026-01-01');new=release('a',new_data,'2.0')
        repo,folder,catalog=fixture(Path(tmp),[old,new],{new['files'][0]['url']:new_data})
        (folder/'a-old.jar').write_bytes(old_data);plan=build_plan(catalog,folder,[new],'1.21.1','fabric')
        stage=apply_plan(repo,'fixture',plan);assert not (folder/'a-old.jar').exists()
        assert (folder/'a-2.0.jar').read_bytes()==new_data
        assert (stage/'backup/a-old.jar').read_bytes()==old_data
        assert undo_last(repo,'fixture')==1 and (folder/'a-old.jar').read_bytes()==old_data
        assert not (folder/'a-2.0.jar').exists()


def test_failed_download_cancel_and_stale_preview_do_not_mutate():
    with tempfile.TemporaryDirectory() as tmp:
        data=jar('a');new=release('a',data);repo,folder,catalog=fixture(Path(tmp),[new],{new['files'][0]['url']:data})
        plan=build_plan(catalog,folder,[new],'1.21.1','fabric');catalog.fail=True
        try:apply_plan(repo,'fixture',plan);assert False
        except OSError:pass
        assert not list(folder.iterdir());catalog.fail=False
        event=threading.Event();event.set()
        try:apply_plan(repo,'fixture',plan,type('Job',(),dict(cancel=event))());assert False
        except DownloadCancelled:pass
        assert not list(folder.iterdir())
        (folder/'user.jar').write_bytes(jar('user'))
        try:apply_plan(repo,'fixture',plan);assert False
        except RuntimeError:pass
        assert (folder/'user.jar').exists()


def test_publish_failure_rolls_back_all_moves():
    with tempfile.TemporaryDirectory() as tmp:
        olddata=jar('a');newdata=jar('a','2.0');old=release('a',olddata);new=release('a',newdata,'2.0')
        repo,folder,catalog=fixture(Path(tmp),[old,new],{new['files'][0]['url']:newdata});(folder/'a-old.jar').write_bytes(olddata)
        plan=build_plan(catalog,folder,[new],'1.21.1','fabric');rename=Path.rename
        def fail(source,target):
            if source.parent.name=='incoming':raise OSError('fixture publication failure')
            return rename(source,target)
        with patch.object(Path,'rename',fail):
            try:apply_plan(repo,'fixture',plan);assert False
            except OSError:pass
        assert (folder/'a-old.jar').read_bytes()==olddata and not (folder/'a-2.0.jar').exists()


def test_recovery_after_simulated_power_loss():
    with tempfile.TemporaryDirectory() as tmp:
        olddata=jar('a');newdata=jar('a','2.0');repo,folder,catalog=fixture(Path(tmp));stage=repo.game_dir/'.onion/mod-changes/power-loss';(stage/'backup').mkdir(parents=True)
        (stage/'backup/old.jar').write_bytes(olddata);(folder/'new.jar').write_bytes(newdata)
        journal=dict(status='applying',version='fixture',folder=str(folder.relative_to(repo.game_dir)),old={'old.jar':hashlib.sha1(olddata).hexdigest()},new={'new.jar':hashlib.sha1(newdata).hexdigest()})
        (stage/'journal.json').write_text(json.dumps(journal));assert recover_interrupted(repo,'fixture')==1
        assert (folder/'old.jar').read_bytes()==olddata and not (folder/'new.jar').exists()


def test_undo_refuses_user_changes():
    with tempfile.TemporaryDirectory() as tmp:
        data=jar('a');new=release('a',data);repo,folder,catalog=fixture(Path(tmp),[new],{new['files'][0]['url']:data})
        apply_plan(repo,'fixture',build_plan(catalog,folder,[new],'1.21.1','fabric'))
        (folder/'a-1.0.jar').write_bytes(jar('user'))
        try:undo_last(repo,'fixture');assert False
        except ValueError:pass
        assert (folder/'a-1.0.jar').read_bytes()==jar('user')


def test_updates_identify_with_get_and_do_not_downgrade():
    with tempfile.TemporaryDirectory() as tmp:
        data=jar('a');old=release('a',data,date='2026-01-01');new=release('a',jar('a','2'),'2');beta=release('a',jar('a','3'),'3',date='2026-11-01');beta['version_type']='beta'
        repo,folder,catalog=fixture(Path(tmp),[old,new,beta]);(folder/'a.jar').write_bytes(data)
        result,unknown=updates(catalog,folder,'1.21.1','fabric');assert not unknown and result[0]['latest']['id']==new['id']
        assert updates(catalog,folder,'1.21.1','fabric',allow_preview=True)[0][0]['latest']['id']==beta['id']
        assert any('/version_file/' in url and '?algorithm=sha1' in url for url in catalog.calls)


def test_favorites_tags_are_scoped_and_survive_restart():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);path=base/'onionmcl.json';a=InstanceStore(path,base/'a');b=InstanceStore(path,base/'b')
        a.update('same',favorite=True,tags='优化，生存,优化');b.update('same',tags=['另一个目录'])
        assert InstanceStore(path,base/'a').get('same').favorite
        assert InstanceStore(path,base/'a').get('same').tags==['优化','生存']
        assert not InstanceStore(path,base/'b').get('same').favorite
        assert normalize_tags([' A ','a',7,'B'])==['A','B']


def test_skin_favorite_identity_survives_rename():
    from tests.test_workshop import png
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp);source=base/'skin.png';source.write_bytes(png(64,64));library=SkinLibrary(base);path=library.import_skin(source)
        library.set_favorite(path,True);assert SkinLibrary(base).is_favorite(path)
        renamed=path.with_name('renamed.png');path.rename(renamed);assert library.is_favorite(renamed)
        library.set_favorite(renamed,False);assert not library.is_favorite(renamed)


def test_task_history_is_bounded_and_marks_interrupted():
    with tempfile.TemporaryDirectory() as tmp:
        history=TaskHistory(tmp)
        for i in range(105):
            record=history.begin('下载 '+str(i),'fixture','instance');history.finish(record,'complete')
        assert len(history.items)==100
        item=history.begin('未结束','fixture','instance');history.progress(item,'access_token=secret');history.save()
        again=TaskHistory(tmp);assert again.items[-1]['state']=='interrupted'
        assert 'secret' not in again.path.read_text(encoding='utf-8')
        again.clear_finished();assert not again.items


def test_crash_report_uses_latest_log_and_redacts_credentials():
    from launcher.crash import reports,redact
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'logs').mkdir();(root/'logs/latest.log').write_text('OptiFine loaded\njava.lang.OutOfMemoryError: Java heap space access_token=secret\n',encoding='utf-8')
        result=reports(root);assert any(i['id']=='out_of_memory' for i in result)
        assert not any(i['id']=='shader_error' for i in result)
        assert 'secret' not in str(result)
        assert 'private' not in redact('--accessToken private')
        assert 'quoted-secret' not in redact('"access_token": "quoted-secret"')


def test_task_history_ignores_malformed_records():
    with tempfile.TemporaryDirectory() as tmp:
        history=TaskHistory(tmp);history.path.parent.mkdir(parents=True)
        history.path.write_text(json.dumps([dict(id='bad',state='complete',started='not a date'),dict(id='ok',state='failed',started=1,detail='password="secret"')]))
        again=TaskHistory(tmp);assert len(again.items)==1 and 'secret' not in again.items[0]['detail']


def test_universal_jar_uses_target_loader_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'universal.jar'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('fabric.mod.json',json.dumps(dict(id='fabric-part',version='1.0',depends={'fabricloader':'>=0.16'})))
            z.writestr('META-INF/mods.toml','[[mods]]\nmodId="forge_part"\nversion="1.0"')
        assert inspect_jar(path,'forge')[0].loader=='forge'
        assert not [i for i in audit(Path(tmp),'1.21.1','forge','52') if i.severity=='error']


def test_quilt_alias_versions_and_conditional_dependencies():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'quilt.jar'
        with zipfile.ZipFile(path,'w') as z:z.writestr('quilt.mod.json',json.dumps(dict(quilt_loader=dict(id='q',version='1.0',provides=[dict(id='alias',version='3.0'),'simple'],depends=[dict(id='conditional',versions='*',unless='other')]))))
        metadata=inspect_jar(path,'quilt');assert metadata[0].uncertain and metadata[0].aliases==['simple']
        assert metadata[1].id=='alias' and metadata[1].version=='3.0'
        assert any(i.code=='unsupported' for i in audit(Path(tmp),loader='quilt'))


def test_retry_reuses_the_same_plan_staging_directory():
    with tempfile.TemporaryDirectory() as tmp:
        data=jar('a');version=release('a',data);repo,folder,dl=fixture(Path(tmp),[version],{version['files'][0]['url']:data})
        plan=build_plan(dl,folder,[version],'1.21.1','fabric');dl.fail=True
        try:apply_plan(repo,'fixture',plan);assert False
        except OSError:pass
        dl.fail=False;stage=apply_plan(repo,'fixture',plan)
        assert stage.name==plan['id'] and len(list(stage.parent.iterdir()))==1


def test_preflight_detects_memory_arguments_and_missing_dependency():
    from launcher.preflight import inspect
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,_=fixture(Path(tmp));(folder/'a.jar').write_bytes(jar('a',depends={'b':'*'}))
        issues=inspect(repo,'fixture',dict(min_memory=4096,max_memory=1024,jvm_args='"broken',java_path=''))
        assert {'memory','arguments','missing'}<={i.code for i in issues}


def test_preflight_accepts_shared_game_root_and_read_only_checks():
    from launcher.preflight import inspect
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,_=fixture(Path(tmp));folder.rmdir();repo.config.set('version_isolation',False)
        assert repo.run_dir('fixture')==repo.game_dir
        issues=inspect(repo,'fixture',dict(min_memory=512,max_memory=2048,java_path=''),write_probe=True)
        assert not [i for i in issues if i.code in ('directory','writable')]
        assert not (repo.game_dir/'.onion-preflight-probe').exists()


def test_shared_mods_cannot_bypass_another_instance_lock_or_interrupted_change():
    from launcher.mod_plan import assert_mods_idle
    from launcher.preflight import inspect
    with tempfile.TemporaryDirectory() as tmp:
        repo,folder,_=fixture(Path(tmp));folder.rmdir();repo.config.set('version_isolation',False)
        other=repo.versions_dir/'other';other.mkdir();(other/'other.json').write_text(json.dumps(dict(id='other',mainClass='Main',libraries=[])))
        def check(vid):
            if vid=='other':raise RuntimeError('Other shared instance is running')
        with patch.object(repo,'assert_idle',side_effect=check):
            try:assert_mods_idle(repo,'fixture');assert False
            except RuntimeError:pass
        stage=repo.game_dir/'.onion/mod-changes/interrupted';stage.mkdir(parents=True)
        (stage/'journal.json').write_text(json.dumps(dict(status='applying',version='other',folder='mods',old={},new={})))
        issues=inspect(repo,'fixture',dict(min_memory=512,max_memory=2048))
        assert any(i.code=='interrupted' for i in issues)
        assert recover_interrupted(repo,'fixture')==0
