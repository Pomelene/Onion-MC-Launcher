"""Security boundaries exercised with disposable files and synthetic secrets."""
import gzip
import hashlib
import io
import json
import os
import struct
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from launcher.accounts import AccountRecord,AccountStore
from launcher.archives import ArchiveLimits,validate_archive,copy_member,read_member
from launcher.auth import authlib
from launcher.download import Downloader,DownloadJob,DownloadError,DownloadCancelled
from launcher.network import validate_url,SafeRedirectHandler
from launcher.secrets import SecretStorageError
from launcher.worlds import read_level_dat
from tests.harness import FakeServer,temp_workspace


def _online():
    return AccountRecord('microsoft','Fixture','a'*32,access_token='fixture-secret-access',refresh_token='fixture-secret-refresh')


def test_windows_credentials_roundtrip_and_legacy_migration():
    if os.name!='nt':return
    with temp_workspace() as root:
        path=root/'accounts.json';record=_online()
        path.write_text(json.dumps({'current':record.uuid,'accounts':[asdict(record)]}))
        store=AccountStore(path);raw=path.read_text()
        assert 'fixture-secret' not in raw and 'windows-dpapi-v1' in raw
        loaded=AccountStore(path).current()
        assert loaded.access_token==record.access_token and loaded.refresh_token==record.refresh_token
        assert list(root.iterdir())==[path],'migration left a plaintext backup or temporary file'


def test_encryption_failure_keeps_original_file_and_memory():
    with temp_workspace() as root:
        store=AccountStore(root/'accounts.json')
        store.add(AccountRecord('offline','Offline','b'*32));before=store.path.read_bytes()
        with patch('launcher.accounts.protect',side_effect=SecretStorageError('unavailable')):
            try:store.add(_online())
            except SecretStorageError:pass
            else:raise AssertionError('encryption silently fell back to plaintext')
        assert store.path.read_bytes()==before
        assert len(store.accounts)==1 and store.current_uuid=='b'*32


def test_unreadable_credentials_are_retained_without_plaintext_fallback():
    with temp_workspace() as root:
        path=root/'accounts.json';record=_online();item=asdict(record)
        for key in ('access_token','refresh_token','client_token'):item.pop(key)
        envelope={'scheme':'windows-dpapi-v1','data':'fixture-ciphertext'};item['protected_secrets']=envelope
        path.write_text(json.dumps({'accounts':[item],'current':record.uuid}))
        with patch('launcher.accounts.unprotect',side_effect=SecretStorageError('different user')):
            store=AccountStore(path)
        assert not store.current().access_token and store.current().is_expired()
        store.save();saved=json.loads(path.read_text())
        assert saved['accounts'][0]['protected_secrets']==envelope


def test_non_windows_refuses_plaintext_online_storage():
    from launcher.secrets import protect
    with patch('launcher.secrets.os.name','posix'):
        try:protect({'access_token':'fixture-secret'})
        except SecretStorageError:pass
        else:raise AssertionError('unsupported platform persisted a secret')


def test_remote_url_rejects_local_files_credentials_and_invalid_ports():
    for url in ('file:///private/file','ftp://example.com/file','data:text/plain,test',
                'https://user:password@example.com/x','https://example.com:bad/x','https://example.com\r\nx'):
        try:validate_url(url)
        except ValueError:pass
        else:raise AssertionError('unsafe remote URL accepted')


def test_redirect_strips_credentials_across_origins_and_rejects_downgrade():
    handler=SafeRedirectHandler()
    req=urllib.request.Request('https://first.example/file',headers={'Authorization':'Bearer fixture','x-api-key':'fixture','Cookie':'fixture'})
    target=handler.redirect_request(req,None,302,'',{},'https://second.example/file')
    assert not any(key.lower() in ('authorization','x-api-key','cookie') for key in target.headers)
    same=handler.redirect_request(req,None,302,'',{},'https://first.example/new')
    assert same.has_header('Authorization')
    for url in ('http://second.example/file','file:///private/file'):
        try:handler.redirect_request(req,None,302,'',{},url)
        except ValueError:pass
        else:raise AssertionError('unsafe redirect accepted')


def test_file_download_rejected_before_writing():
    with temp_workspace() as root:
        source=root/'source';source.write_text('private fixture')
        try:Downloader().download_one(DownloadJob(source.as_uri(),root/'target'))
        except ValueError:pass
        else:raise AssertionError('local file treated as remote download')
        assert not (root/'target').exists()


def test_sha256_cache_and_download_integrity():
    data=b'verified-content';digest=hashlib.sha256(data).hexdigest()
    server=FakeServer({'/file':data}).start()
    try:
        with temp_workspace() as root:
            target=root/'file';target.write_bytes(b'tampered')
            dl=Downloader(retries=1);job=DownloadJob(server.url('/file'),target,sha256=digest,size=len(data))
            dl.download_one(job);assert target.read_bytes()==data
            count=len(server.requests);dl.download_one(job);assert len(server.requests)==count
    finally:server.stop()


def test_authlib_does_not_echo_raw_error_or_accept_http():
    error=urllib.error.HTTPError('https://example.invalid',400,'bad',{},io.BytesIO(b'fixture-secret-password'))
    with patch.object(authlib,'secure_open',side_effect=error):
        try:authlib._post_json('https://example.invalid',{})
        except DownloadError as exc:assert 'fixture-secret' not in str(exc)
        else:raise AssertionError('server error ignored')
    with patch.object(authlib,'_post_json') as posted:
        try:authlib.authenticate('http://example.invalid','fixture','fixture-password')
        except ValueError:pass
        else:raise AssertionError('credentials sent over HTTP')
        posted.assert_not_called()


def test_injector_always_requests_pinned_digest_even_for_existing_cache():
    with temp_workspace() as root:
        target=root/'injector.jar';target.write_bytes(b'untrusted-cache');seen=[]
        class Capture:
            def download_one(self,job):seen.append(job)
        authlib.ensure_injector(Capture(),target)
        assert len(seen)==1 and seen[0].sha256==authlib.INJECTOR_SHA256
        assert '/latest/' not in seen[0].url and seen[0].size==authlib.INJECTOR_SIZE


def test_archive_budget_rejects_before_extraction():
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w') as archive:archive.writestr('file',b'x'*64)
    memory.seek(0)
    with zipfile.ZipFile(memory) as archive:
        for limits in (ArchiveLimits(member_bytes=32),ArchiveLimits(total_bytes=32),ArchiveLimits(members=0)):
            try:validate_archive(archive,limits)
            except ValueError:pass
            else:raise AssertionError('archive exceeded configured resource budget')
        try:read_member(archive,'file',limit=32)
        except ValueError:pass
        else:raise AssertionError('oversized archive metadata read')


def test_archive_cancellation_and_error_preserve_existing_destination():
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w') as archive:archive.writestr('file',b'x'*64)
    memory.seek(0)
    with temp_workspace() as root,zipfile.ZipFile(memory) as archive:
        target=root/'existing';target.write_bytes(b'keep');cancel=threading.Event();cancel.set()
        try:copy_member(archive,archive.getinfo('file'),target,cancel_event=cancel)
        except DownloadCancelled:pass
        else:raise AssertionError('archive ignored cancellation')
        assert target.read_bytes()==b'keep' and list(root.iterdir())==[target]
        try:copy_member(archive,archive.getinfo('file'),target,limit=32)
        except ValueError:pass
        else:raise AssertionError('archive ignored streaming limit')
        assert target.read_bytes()==b'keep' and list(root.iterdir())==[target]


def test_archive_rejects_extreme_ratio_without_expanding_payload():
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('file',b'x'*(2*1024**2))
    memory.seek(0)
    with zipfile.ZipFile(memory) as archive:
        try:validate_archive(archive,ArchiveLimits(ratio=10))
        except ValueError:pass
        else:raise AssertionError('abnormal compression ratio accepted')


def test_nbt_rejects_oversized_array_and_deep_nesting():
    # Root compound, unnamed byte array with an enormous declared size. No large allocation.
    payload=b'\x0a\x00\x00\x07\x00\x00'+struct.pack('>i',2**30)
    with temp_workspace() as root:
        path=root/'level.dat';path.write_bytes(gzip.compress(payload));assert read_level_dat(path)=={}
        nested=b'\x0a\x00\x00'*70+b'\x00'*70
        path.write_bytes(gzip.compress(nested));assert read_level_dat(path)=={}


def test_java_manifest_path_cannot_escape_runtime_directory():
    from launcher.java import download_java,JAVA_COMPONENTS,_platform_key
    with temp_workspace() as root:
        dest=root/'runtime/component';calls=[]
        manifest={_platform_key():{JAVA_COMPONENTS[21]:[{'manifest':{'url':'https://example.invalid/manifest'}}]}}
        malicious={'files':{'../../outside':{'type':'file','downloads':{'raw':{'url':'https://example.invalid/fake'}}}}}
        class Fake:
            def fetch_json(self,url):calls.append(url);return manifest if len(calls)==1 else malicious
            def download_many(self,*args,**kwargs):raise AssertionError('unsafe job dispatched')
        with patch('launcher.java.runtime_dir',return_value=dest):
            try:download_java(21,Fake())
            except (ValueError,PermissionError):pass
            else:raise AssertionError('runtime path escaped its root')
        assert not (root/'outside').exists()


def test_api_key_migration_uses_secure_storage():
    if os.name!='nt':return
    from launcher.config import Config
    with temp_workspace() as root:
        path=root/'settings.json';path.write_text(json.dumps({'curseforge_api_key':'fixture-private-key'}))
        config=Config(path)
        assert 'fixture-private-key' not in path.read_text()
        assert config.get('curseforge_api_key')=='fixture-private-key'
        assert Config(path).get('curseforge_api_key')=='fixture-private-key'


def test_missing_online_credentials_cannot_launch_as_offline():
    from launcher.launch import Account,LaunchSettings,launch
    for kind in ('msa','mojang'):
        try:launch(None,None,Account('Fixture','a'*32,access_token='',user_type=kind),LaunchSettings(),'not-executed')
        except PermissionError:pass
        else:raise AssertionError('unreadable online credentials were downgraded')


def test_failed_digest_download_preserves_existing_file():
    server=FakeServer({'/file':b'tampered'}).start()
    try:
        with temp_workspace() as root:
            target=root/'file';target.write_bytes(b'keep-original')
            try:Downloader(retries=1).download_one(DownloadJob(server.url('/file'),target,sha256='0'*64))
            except DownloadError:pass
            else:raise AssertionError('mismatched SHA-256 published')
            assert target.read_bytes()==b'keep-original'
    finally:server.stop()


def test_archive_disk_reserve_preserves_existing_file():
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w') as archive:archive.writestr('file',b'fixture')
    memory.seek(0)
    from types import SimpleNamespace
    with temp_workspace() as root,zipfile.ZipFile(memory) as archive:
        target=root/'existing';target.write_bytes(b'keep')
        with patch('launcher.archives.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            try:copy_member(archive,archive.getinfo('file'),target)
            except ValueError:pass
            else:raise AssertionError('disk reserve ignored')
        assert target.read_bytes()==b'keep'
