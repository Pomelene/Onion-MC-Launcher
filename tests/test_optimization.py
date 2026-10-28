"""Performance changes must preserve integrity, cancellation and result choices."""
import hashlib,io,json,threading,tempfile
from pathlib import Path
from unittest.mock import patch
from launcher.assets import AssetIndex
from launcher.download import DownloadJob,Downloader,DownloadError
from launcher.mod_plan import updates
from tests.test_next_features import Catalog,jar,release


def test_asset_scan_handles_duplicates_size_changes_and_missing_prefixes():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);digest=hashlib.sha1(b'asset').hexdigest()
        data={'objects':{'first':{'hash':digest,'size':5},'alias':{'hash':digest,'size':5}}}
        index=AssetIndex.parse(data)
        assert len(index.jobs(root))==1
        target=root/digest[:2]/digest;target.parent.mkdir();target.write_bytes(b'asset')
        assert not index.jobs(root)
        target.write_bytes(b'wrong size');assert len(index.jobs(root))==1


def test_hash_validation_rejects_wrong_size_before_reading_and_checks_both_hashes():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'file';path.write_bytes(b'payload')
        job=DownloadJob('https://example.com',path,size=8,sha1='0'*40)
        with patch.object(Path,'open',side_effect=AssertionError('unnecessary read')):
            assert not Downloader._hash_valid(path,job)
        job.size=7;job.sha1=hashlib.sha1(b'payload').hexdigest();job.sha256=hashlib.sha256(b'payload').hexdigest()
        assert Downloader._hash_valid(path,job)
        job.sha256='0'*64;assert not Downloader._hash_valid(path,job)


def test_stream_download_rejects_wrong_range_without_publishing_file():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'file';path.with_name('file.part').write_bytes(b'old')
        class Response(io.BytesIO):
            status=206
            headers={'Content-Length':'3','Content-Range':'bytes 2-4/5'}
        opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b'new')})()
        with patch.object(Downloader,'_opener',return_value=opener):
            try:Downloader(retries=1).download_one(DownloadJob('https://example.com',path))
            except DownloadError:pass
            else:raise AssertionError('wrong range was accepted')
        assert not path.exists() and not path.with_name('file.part').exists()


def test_batch_mod_updates_match_per_file_results_and_channel_filters():
    versions=[]
    class Batch(Catalog):
        def __init__(self):super().__init__(versions,{});self.posts=[]
        def post_json(self,url,payload):
            self.posts.append((url,payload))
            found={}
            for digest in payload['hashes']:
                current=next((v for v in self.versions if v['files'][0]['hashes']['sha1']==digest),None)
                if current is None:continue
                if url.endswith('/update'):
                    candidates=[v for v in self.versions if v['project_id']==current['project_id'] and v['version_type'] in payload['version_types']]
                    current=max(candidates,key=lambda v:v['date_published'])
                found[digest]=current
            return found
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for index in range(12):
            key='mod'+str(index);data=jar(key);(root/(key+'.jar')).write_bytes(data)
            versions.extend([release(key,data,date='2025-01-01'),release(key,jar(key,'2.0'),'2.0',date='2026-01-01')])
            beta=release(key,jar(key,'3.0'),'3.0',date='2026-02-01');beta['version_type']='beta';versions.append(beta)
        expected=updates(Catalog(versions,{}),root,'1.21.1','fabric')
        remote=Batch();actual=updates(remote,root,'1.21.1','fabric')
        assert actual==expected and len(actual[0])==12
        assert len(remote.posts)==2 and not remote.calls
        assert remote.posts[1][1]['version_types']==['release']
        result,_=updates(remote,root,'1.21.1','fabric',allow_preview=True)
        assert all(item['latest']['version_number']=='3.0' for item in result)


def test_mod_summary_metadata_is_bounded_and_cache_tracks_changes():
    import zipfile,os
    from launcher.mods import read_mod_info
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'mod.jar';path.write_bytes(jar('a'))
        with patch('launcher.mods.zipfile.ZipFile',wraps=zipfile.ZipFile) as opened:
            first=read_mod_info(path);first.name='mutated'
            assert read_mod_info(path).name=='a' and opened.call_count==1
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as out:
            out.writestr('fabric.mod.json',b' '*1000000)
        assert read_mod_info(path).name=='mod'


def test_deferred_runtime_restores_identical_files_and_rejects_corruption():
    import runpy,lzma
    restore=runpy.run_path(str(Path(__file__).resolve().parents[1]/'packaging/qt_unpack.py'))['restore']
    for broken in (False,True):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=root/'qt-payload';payload.mkdir()
            first=b'first DLL contents';second=b'another payload'
            (payload/'runtime.xz').write_bytes(lzma.compress(first+second))
            entries=[{'path':'a.dll','size':len(first),'sha256':hashlib.sha256(first).hexdigest()},
                     {'path':'plugins/b.dll','size':len(second),'sha256':hashlib.sha256(second).hexdigest()}]
            if broken:entries[1]['sha256']='0'*64
            (payload/'manifest.json').write_text(json.dumps([{'source':'qt-payload/runtime.xz','files':entries}]))
            if broken:
                try:restore(root)
                except RuntimeError:pass
                else:raise AssertionError('corrupted runtime accepted')
                assert not (root/'plugins/b.dll').exists()
            else:
                restore(root);assert (root/'a.dll').read_bytes()==first and (root/'plugins/b.dll').read_bytes()==second
                assert not (payload/'runtime.xz').exists()
                restore(root)  # A worker subprocess can reuse the verified runtime.


def test_launcher_log_formatter_redacts_formatted_secrets_and_tracebacks():
    import logging
    from launcher.log import SafeFormatter
    formatter=SafeFormatter('%(message)s')
    record=logging.LogRecord('test',logging.INFO,'',0,'access_token=%s Authorization: Bearer %s',('token-fixture','bearer-fixture'),None)
    text=formatter.format(record)
    assert 'token-fixture' not in text and 'bearer-fixture' not in text
    record=logging.LogRecord('test',logging.INFO,'',0,'x-api-key="api-fixture" client_token=client-fixture password=pw-fixture',(),None)
    text=formatter.format(record)
    assert not any(value in text for value in ('api-fixture','client-fixture','pw-fixture'))


def test_game_log_pump_redacts_tokens_and_bounds_single_lines():
    from launcher.launch import ManagedProcess
    process=object.__new__(ManagedProcess);lines=[];process._on_log=lambda line,error:lines.append(line)
    process._pump(io.BytesIO(b'access_token=secret-fixture\n'+b'x'*(600*1024)),False)
    assert lines and 'secret-fixture' not in lines[0] and max(map(len,lines))<=256*1024


def test_runtime_manifest_rejects_parent_paths_before_writing():
    import runpy
    restore=runpy.run_path(str(Path(__file__).resolve().parents[1]/'packaging/qt_unpack.py'))['restore']
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);(root/'qt-payload').mkdir()
        data=[{'source':'qt-payload/runtime.xz','files':[{'path':'../escape.dll','size':1,'sha256':'0'*64}]}]
        (root/'qt-payload/manifest.json').write_text(json.dumps(data))
        try:restore(root)
        except RuntimeError:pass
        else:raise AssertionError('runtime path escaped extraction root')


def test_tls_configuration_reuse_keeps_verification_and_refreshes_trust():
    import ssl
    import launcher.network as network
    with patch.object(network,'_TLS_CONTEXT',None),patch.object(network,'_TLS_CREATED',0.0),patch.object(network.ssl,'create_default_context',wraps=ssl.create_default_context) as create:
        first=network.https_handler()._context;second=network.https_handler()._context
        assert first is second and create.call_count==1
        assert first.check_hostname and first.verify_mode==ssl.CERT_REQUIRED
        with patch.object(network.time,'monotonic',return_value=network._TLS_CREATED+301):
            third=network.https_handler()._context
        assert third is not first and third.check_hostname and third.verify_mode==ssl.CERT_REQUIRED


def test_java_discovery_preserves_known_layouts_and_excludes_library_trees():
    import os
    import launcher.java as java
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);name='java.exe' if os.name=='nt' else 'java';expected=[]
        for layout in ('jdk-21','jdk-25/jbr','jdk-mac/Contents/Home'):
            path=root/layout/'bin'/name;path.parent.mkdir(parents=True);path.write_bytes(b'fixture');expected.append(path.resolve())
        hidden=root/'lib'/'ignored'/'bin'/name;hidden.parent.mkdir(parents=True);hidden.write_bytes(b'fixture')
        with patch.object(java,'_registry_homes',return_value=[]),patch.object(java,'_search_roots',return_value=[root]),patch.dict(os.environ,{'PATH':'','JAVA_HOME':'','JRE_HOME':'','JDK_HOME':''}):
            assert set(java._candidate_paths())==set(expected)
            cancelled=threading.Event();cancelled.set();assert java._candidate_paths(cancel_event=cancelled)==[]


def test_crash_file_is_read_once_and_large_reports_are_bounded():
    from launcher.crash import _report_text,diagnose_file
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'crash.txt';path.write_bytes(b'Description: fixture\n'+b'x'*(5*1024**2)+b'\nJava Version: 21\n')
        text=_report_text(path)
        assert len(text)<4*1024**2+100 and text.startswith('Description: fixture') and text.endswith('Java Version: 21\n')
        with patch('launcher.crash._report_text',return_value='Description: fixture\nJava Version: 21\n') as read:
            diagnose_file(path);read.assert_called_once_with(path)


def test_native_reuse_verifies_source_and_destination_bytes():
    import zipfile
    from launcher.natives import extract_native
    from launcher.libraries import Library
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);source=root/'native.jar';target=root/'natives';library=Library.from_json({'name':'org.test:native:1'})
        with zipfile.ZipFile(source,'w') as archive:archive.writestr('test.dll',b'original')
        assert extract_native(library,source,target)==1
        with patch('launcher.natives.copy_member',side_effect=AssertionError('unneeded extraction')):
            assert extract_native(library,source,target)==0
        (target/'test.dll').write_bytes(b'modified')
        assert extract_native(library,source,target)==1 and (target/'test.dll').read_bytes()==b'original'
        with zipfile.ZipFile(source,'w') as archive:archive.writestr('test.dll',b'updated!')
        assert extract_native(library,source,target)==1 and (target/'test.dll').read_bytes()==b'updated!'


def test_reference_asset_coverage_detects_removed_or_wrong_size_files():
    from launcher.repository import GameRepository
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);digest=hashlib.sha1(b'asset').hexdigest();target=root/'objects'/digest[:2]/digest
        target.parent.mkdir(parents=True);target.write_bytes(b'asset')
        index=root/'index.json';index.write_text(json.dumps({'objects':{'entry':{'hash':digest,'size':5}}}))
        repo=object.__new__(GameRepository)
        assert repo._reference_covers_index(index,root)
        target.write_bytes(b'wrong size');assert not repo._reference_covers_index(index,root)
        target.write_bytes(b'asset');assert repo._reference_covers_index(index,root)
        target.unlink();assert not repo._reference_covers_index(index,root)


def test_fetch_cancels_between_stream_reads_without_changing_error_type():
    from launcher.download import DownloadCancelled
    cancel=threading.Event()
    class Response(io.BytesIO):
        def read1(self,n):cancel.set();return super().read1(n)
    opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b'body')})()
    downloader=Downloader(retries=1)
    with patch.object(downloader,'_opener',return_value=opener),downloader.cancellable(cancel):
        try:downloader.fetch('https://example.invalid')
        except DownloadCancelled:pass
        else:raise AssertionError('request ignored cancellation during read')


def test_fetch_retry_keeps_original_post_body():
    from unittest.mock import Mock
    opener=Mock();opener.open.side_effect=[io.BytesIO(b'\xff'),io.BytesIO(b'ok')]
    downloader=Downloader(retries=2)
    with patch.object(downloader,'_opener',return_value=opener):
        assert downloader.fetch('https://example.invalid',data=b'original-request',method='POST')=='ok'
    assert [call.args[0].data for call in opener.open.call_args_list]==[b'original-request',b'original-request']


def test_content_icon_cache_is_bounded_and_rechecks_changed_archives():
    import zipfile
    from launcher.qtui.content_icons import read_content_icon
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'icon.jar'
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('pack.png',b'first-icon')
        with patch('launcher.qtui.content_icons.zipfile.ZipFile',wraps=zipfile.ZipFile) as opened:
            assert read_content_icon(path)==read_content_icon(path)==b'first-icon' and opened.call_count==1
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('pack.png',b'updated-icon')
        assert read_content_icon(path)==b'updated-icon'


def test_corrupt_same_size_asset_index_is_repaired_with_metadata_limits():
    from launcher.config import Config
    from launcher.repository import GameRepository
    from launcher.version import ResolvedVersion
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);config=Config(root/'settings.json');config.set('game_dir',str(root/'game'));repo=GameRepository(config)
        body=b'{"objects":{}}';index=repo.assets_dir/'indexes/test.json';index.parent.mkdir(parents=True);index.write_bytes(b'x'*len(body))
        version=ResolvedVersion(id='test',asset_index={'id':'test','url':'https://example.invalid/index','size':len(body)})
        def repair(job):
            assert job.force and job.max_size==32*1024**2
            job.path.write_bytes(body)
        with patch.object(repo.downloader,'download_one',side_effect=repair) as download:
            repo._ensure_assets(version);download.assert_called_once()


def test_forced_download_replaces_bad_equal_size_cache_and_preserves_original():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'file';path.write_bytes(b'old!');path.with_name('file.part').write_bytes(b'bad-part')
        class Response(io.BytesIO):
            status=200;headers={'Content-Length':'4'}
        opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b'new!')})()
        with patch.object(Downloader,'_opener',return_value=opener):
            Downloader(retries=1).download_one(DownloadJob('https://example.invalid',path,size=4,force=True,max_size=8))
        assert path.read_bytes()==b'new!' and any(p.read_bytes()==b'old!' for p in (path.parent/'.craftbridge-backups').iterdir())


def test_download_rejects_oversized_declared_body_before_writing():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'file'
        class Response(io.BytesIO):
            status=200;headers={'Content-Length':'100'}
        opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b'body')})()
        with patch.object(Downloader,'_opener',return_value=opener):
            try:Downloader(retries=1).download_one(DownloadJob('https://example.invalid',path,max_size=8))
            except DownloadError:pass
            else:raise AssertionError('oversized response was accepted')
        assert not path.exists() and not path.with_name('file.part').exists()


def test_batch_network_failure_is_not_reported_as_no_updates():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);path=root/'mod.jar';path.write_bytes(jar('test'))
        class Remote:
            threads=1
            def post_json(self,*args):raise DownloadError('offline fixture')
        try:updates(Remote(),root,'1.21.1','fabric')
        except DownloadError:pass
        else:raise AssertionError('network failure was treated as an empty update list')
        assert path.read_bytes()==jar('test')


def test_legacy_secret_migration_does_not_silence_failed_atomic_save():
    from launcher.config import Config
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'settings.json';body=json.dumps({'curseforge_api_key':'fixture-private-key'})
        path.write_text(body)
        with patch.object(Config,'save',side_effect=PermissionError('fixture denied')):
            try:Config(path)
            except PermissionError:pass
            else:raise AssertionError('credential migration silently ignored failed save')
        assert path.read_text()==body


def test_download_cancellation_at_response_close_preserves_original():
    from launcher.download import DownloadCancelled
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'file';path.write_bytes(b'old!');cancel=threading.Event()
        class Response(io.BytesIO):
            status=200;headers={'Content-Length':'4'}
            def __exit__(self,*args):
                cancel.set();return super().__exit__(*args)
        opener=type('Opener',(),{'open':lambda *args,**kwargs:Response(b'new!')})()
        with patch.object(Downloader,'_opener',return_value=opener):
            try:Downloader(retries=1).download_one(DownloadJob('https://example.invalid',path,size=4,force=True,cancel_event=cancel))
            except DownloadCancelled:pass
            else:raise AssertionError('cancelled download replaced existing file')
        assert path.read_bytes()==b'old!'


def test_zip_member_with_valid_crc_but_wrong_length_is_not_published():
    import struct,zipfile
    from launcher.archives import copy_member
    source=io.BytesIO()
    with zipfile.ZipFile(source,'w') as archive:archive.writestr('file',b'abc')
    body=bytearray(source.getvalue());central=body.index(b'PK\x01\x02')
    struct.pack_into('<I',body,central+24,4);struct.pack_into('<I',body,22,4)
    with tempfile.TemporaryDirectory() as folder,zipfile.ZipFile(io.BytesIO(body)) as archive:
        path=Path(folder)/'file';path.write_bytes(b'original')
        try:copy_member(archive,archive.getinfo('file'),path)
        except ValueError:pass
        else:raise AssertionError('ZIP member shorter than its declaration was accepted')
        assert path.read_bytes()==b'original' and sorted(p.name for p in path.parent.iterdir())==['file']
