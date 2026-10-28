"""Updater routing, untrusted manifest validation and isolated staging."""
import hashlib
import json
import os
import struct
import tempfile
import threading
import urllib.request
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock

from launcher import updates
from launcher.download import DownloadError,DownloadCancelled,Downloader


def executable_bytes():
    data=bytearray(256);data[:2]=b'MZ';struct.pack_into('<I',data,0x3c,128);data[128:134]=b'PE\0\0\x64\x86'
    return bytes(data)


def entry(version='0.3.3',order=33):
    return dict(series='thunion' if version.endswith('-T') else 'public',version=version,order=order,
        platform='windows-x64',url='https://github.com/Pomelene/Onion-MC-Launcher/releases/download/v'+version+'/Onion.exe',
        size=len(executable_bytes()),sha256=hashlib.sha256(executable_bytes()).hexdigest(),notes='优化外观与体验')


def release():return updates.parse_manifest({'schema_version':1,'releases':[entry()]})[0]


def test_update_filename_refreshes_only_explicit_version_tokens():
    cases={'Onion-v0.4.0.exe':'Onion-v0.5.0-T.exe','自定义 v0.3.0.1-T 测试.EXE':'自定义 v0.5.0-T 测试.EXE',
           'v0.4.0-T.exe':'v0.5.0-T.exe','我的启动器.exe':'我的启动器.exe','Onion-0.4.0.exe':'Onion-0.5.0-T.exe',
           'Onion0.3.0.1-T.exe':'Onion0.5.0-T.exe','Onionv0.4.0.exe':'Onionv0.5.0-T.exe',
           '0.3.0.1.exe':'0.5.0-T.exe','v0.1.2.3.4.exe':'v0.1.2.3.4.exe','0.1.2.3.4.exe':'0.1.2.3.4.exe'}
    for original,expected in cases.items():
        assert updates.updated_executable_path(Path('folder')/original,'0.5.0-T')==Path('folder')/expected
    assert updates.updated_executable_path('v0.5.0-T.exe','0.3.0.1').name=='v0.3.0.1.exe'


def test_update_order_is_numeric_and_isolated_between_editions():
    rows=[entry('0.3.3',33),entry('0.3.10',40),entry('0.3.4-T',100)]
    releases=updates.parse_manifest({'schema_version':1,'releases':rows[::-1]})
    assert updates.select_release(releases,'0.3.2',32).version=='0.3.10'
    assert updates.select_release(releases,'0.3.2-T',32).version=='0.3.4-T'
    assert updates.select_release(releases,'0.3.10',40) is None
    assert updates.select_release(releases,'0.3.11',50) is None
    assert updates.select_release(releases,'0.3.4-T',32) is None
    assert updates.select_release([], '0.3.2',32) is None


def test_manual_history_includes_downgrades_and_other_editions():
    releases=updates.parse_manifest({'schema_version':1,'releases':[entry('0.2.0',1),entry('0.3.3',33),entry('0.3.2-T',32)]})
    choices=updates.available_releases(releases,'0.3.3')
    assert [r.version for r in choices]==['0.3.3','0.2.0','0.3.2-T']
    assert [r.version for r in updates.available_releases(releases,'0.3.3-T')]==['0.3.2-T','0.3.3','0.2.0']
    assert updates.select_release(releases,'0.3.3',33) is None


def test_manifest_rejects_wrong_series_downloads_sizes_and_duplicate_orders():
    for key,value in [('series','other'),('version','0.3.3-T'),('version','latest'),('order',True),('order','33'),
            ('platform','linux-x64'),('size',True),('size',updates.MAX_EXE+1),('sha256','bad'),('notes',{'html':'invalid'}),
            ('url','http://github.com/Pomelene/Onion-MC-Launcher/releases/download/v0.3.3/Onion.exe'),
            ('url','https://github.com.evil.test/Pomelene/Onion-MC-Launcher/releases/download/v0.3.3/Onion.exe'),
            ('url','https://github.com/another/project/releases/download/v0.3.3/Onion.exe'),
            ('url','https://github.com/Pomelene/Onion-MC-Launcher/releases/download/v0.3.3/script.ps1')]:
        item=entry();item[key]=value
        try:updates.parse_manifest({'schema_version':1,'releases':[item]})
        except ValueError:pass
        else:raise AssertionError('Invalid manifest accepted: '+key)
    for data in ([],{'schema_version':True,'releases':[]},{'schema_version':1,'releases':[entry(),entry()]},
                 {'schema_version':1,'releases':[entry()]*129}):
        try:updates.parse_manifest(data)
        except ValueError:pass
        else:raise AssertionError('Invalid manifest accepted')


def test_update_fetch_is_anonymous_fresh_and_bounded():
    data=json.dumps({'schema_version':1,'releases':[entry(),entry('0.3.3-T',33)]}).encode()
    with patch('launcher.updates.fetch_public',return_value=data) as fetch:
        assert updates.check_update(version='0.3.2-T',order=32,proxy='http://localhost:7890').version=='0.3.3-T'
        updates.check_update(version='0.3.2',order=32)
    first,second=fetch.call_args_list
    assert first.args[0].full_url!=second.args[0].full_url
    assert first.kwargs=={'limit':updates.MAX_MANIFEST,'timeout':12,'proxy':'http://localhost:7890'}
    assert not any(key.lower() in ('authorization','cookie') for key in first.args[0].headers)


def test_update_verification_rejects_corrupt_and_wrong_architecture_files():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'update.exe';path.write_bytes(executable_bytes());updates.verify_executable(path,release())
        for body in (b'not executable',b'x'*256,executable_bytes().replace(b'\x64\x86',b'\x4c\x01')):
            path.write_bytes(body);item=replace(release(),size=len(body),sha256=hashlib.sha256(body).hexdigest())
            try:updates.verify_executable(path,item)
            except ValueError:pass
            else:raise AssertionError('Invalid executable accepted')
        path.write_bytes(b'bad')
        try:updates.verify_executable(path,release())
        except ValueError:pass
        else:raise AssertionError('Corrupt executable accepted')


def test_update_download_stages_inside_hidden_directory_and_retries_proxy():
    attempts=[]
    class Transport:
        def __init__(self,**kwargs):attempts.append(kwargs)
        def cancellable(self,*args):return nullcontext()
        def download_one(self,job,progress):
            if len(attempts)==1:raise DownloadError('proxy unavailable')
            job.path.write_bytes(executable_bytes());progress(job.size,job.size)
    task=SimpleNamespace(cancel=threading.Event(),transferred=lambda n:None,emit=lambda data:None)
    with tempfile.TemporaryDirectory() as folder,patch('launcher.updates.Downloader',Transport):
        original=Path(folder)/'Onion.exe';original.write_bytes(b'original')
        staged=updates.download_update(release(),original,Downloader(proxy='http://localhost:7890'),task)
        assert staged.is_relative_to(Path(folder)/'.onion/updates') and original.read_bytes()==b'original'
        assert attempts[0]['proxy']=='http://localhost:7890' and attempts[1]['use_system_proxy'] is False
        updates.verify_executable(staged,release())


def test_failed_or_cancelled_update_never_replaces_original():
    for failure in (DownloadError('offline'),DownloadCancelled('cancelled')):
        task=SimpleNamespace(cancel=threading.Event(),transferred=lambda n:None,emit=lambda data:None)
        with tempfile.TemporaryDirectory() as folder,patch('launcher.updates.Downloader') as transport:
            original=Path(folder)/'Onion.exe';original.write_bytes(b'original')
            transport.return_value.cancellable.return_value=nullcontext()
            transport.return_value.download_one.side_effect=failure
            try:updates.download_update(release(),original,Downloader(),task)
            except type(failure):pass
            else:raise AssertionError('Expected download failure')
            assert original.read_bytes()==b'original' and not list((original.parent/'.onion/updates').rglob('update.exe*'))


def test_update_helper_quotes_special_paths_and_restricts_replacement():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)/"中文 [TARGET] $() 'STAGED'";root.mkdir()
        original=root/'Onion.exe';staged=root/'.onion/updates/pending-fixture/update.exe'
        script=updates.replacement_script(original,staged,release(),123)
        assert updates._ps(original.resolve()) in script and updates._ps(staged.resolve()) in script
        assert '[System.IO.File]::Replace' in script and 'WaitForExit(120000)' in script
        assert '.ComputeHash($stream)' in script and '@@' not in script
        assert "$info.EnvironmentVariables['PYINSTALLER_RESET_ENVIRONMENT']='1'" in script
        for path in (root/'update.exe',root/'outside/update.exe'):
            try:updates.replacement_script(original,path,release(),123)
            except ValueError:pass
            else:raise AssertionError('Update helper accepted an unmanaged path')


def test_update_result_cleanup_preserves_failures_and_acknowledges_once():
    with tempfile.TemporaryDirectory() as folder:
        original=Path(folder)/'Onion.exe';root=Path(folder)/'.onion/updates'
        for state in ('success','failed'):
            pending=root/('pending-'+state);pending.mkdir(parents=True)
            (pending/'result.json').write_text(json.dumps({'result':state}))
            (pending/'previous.exe').write_bytes(b'original')
        assert updates.finish_previous_updates(original)
        assert not (root/'pending-success').exists()
        assert (root/'pending-failed/previous.exe').read_bytes()==b'original'
        assert not updates.finish_previous_updates(original)


def test_update_helper_only_launches_for_current_frozen_executable():
    with patch('launcher.updates.can_install',return_value=False),patch('launcher.updates.subprocess.Popen') as launched:
        try:updates.launch_replacement('not-current.exe','update.exe',release())
        except RuntimeError:pass
        else:raise AssertionError('Source process attempted replacement')
        launched.assert_not_called()


def test_blocked_update_helper_does_not_request_launcher_exit():
    if os.name!='nt':return
    with tempfile.TemporaryDirectory() as folder:
        original=Path(folder)/'Onion.exe';original.write_bytes(b'original')
        staged=Path(folder)/'.onion/updates/pending-fixture/update.exe';staged.parent.mkdir(parents=True);staged.write_bytes(executable_bytes())
        process=Mock();process.poll.return_value=1
        environment_before=dict(os.environ)
        with patch('launcher.updates.can_install',return_value=True),patch('launcher.updates.sys.executable',str(original)),patch('launcher.updates.subprocess.Popen',return_value=process) as launched:
            try:updates.launch_replacement(original,staged,release())
            except RuntimeError as error:assert '保持运行' in str(error)
            else:raise AssertionError('Blocked update helper was accepted')
        assert launched.call_args.kwargs['env']=={**environment_before,'PYINSTALLER_RESET_ENVIRONMENT':'1'}
        assert dict(os.environ)==environment_before
        assert original.read_bytes()==b'original'


def test_direct_update_transport_ignores_system_proxy_without_changing_environment():
    with patch('urllib.request.getproxies',return_value={'https':'http://fixture:7890'}):
        direct=Downloader(use_system_proxy=False)._opener()
        proxies=[handler for handler in direct.handlers if isinstance(handler,urllib.request.ProxyHandler)]
        assert not any(handler.proxies for handler in proxies)
