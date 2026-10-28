"""Concurrency, cache invalidation and cancellation must preserve audit results."""
import os,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
from launcher.parallel import ordered_parallel
from launcher.download import Downloader,DownloadCancelled
from launcher.mod_audit import audit
from launcher.mod_plan import updates,identify
from tests.test_next_features import jar,release,Catalog


def test_parallel_results_keep_input_order_and_obey_worker_limit():
    lock=threading.Lock();barrier=threading.Barrier(4);counts=[0,0]
    def work(value):
        with lock:counts[0]+=1;counts[1]=max(counts)
        if value<4:barrier.wait(timeout=3)
        time.sleep((8-value)*.001)
        with lock:counts[0]-=1
        return value*2
    progress=[]
    assert ordered_parallel(work,range(8),workers=4,progress=lambda n,total:progress.append((n,total)))==list(range(0,16,2))
    assert counts[1]==4 and progress==[(n,8) for n in range(1,9)]


def test_cancel_stops_scheduling_and_never_reports_partial_success():
    cancel=threading.Event();started=[];barrier=threading.Barrier(2)
    def work(value):
        started.append(value);barrier.wait(timeout=3);cancel.set();return value
    try:ordered_parallel(work,range(100),workers=2,cancel=cancel)
    except DownloadCancelled:pass
    else:raise AssertionError('Cancelled check returned partial success')
    assert sorted(started)==[0,1]
    started.clear()
    try:ordered_parallel(work,range(100),workers=2,cancel=cancel)
    except DownloadCancelled:pass
    else:raise AssertionError('Pre-cancelled check ran')
    assert not started


def test_cancel_while_waiting_for_shared_budget_does_not_start_io():
    slots=threading.BoundedSemaphore(1);slots.acquire();cancel=threading.Event();started=[];errors=[]
    def check():
        try:ordered_parallel(lambda item:started.append(item),range(10),workers=4,cancel=cancel,slots=slots)
        except DownloadCancelled:errors.append('cancelled')
    thread=threading.Thread(target=check);thread.start();cancel.set();thread.join(timeout=3)
    slots.release()
    assert not thread.is_alive() and errors==['cancelled'] and not started


def test_metadata_cache_rechecks_changed_files_and_changed_environment():
    import launcher.mod_audit as module
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/'mod.jar';path.write_bytes(jar('a',depends={'java':'>=25'}))
        with patch.object(module,'inspect_jar',wraps=module.inspect_jar) as reader:
            assert not audit(root,java='25');assert reader.call_count==1
            assert any(i.code=='version' for i in audit(root,java='21'));assert reader.call_count==1
            stamp=path.stat().st_mtime_ns
            path.write_bytes(jar('a',depends={'missing':'*'}));os.utime(path,ns=(stamp+10_000_000,stamp+10_000_000))
            assert any(i.code=='missing' for i in audit(root,java='25'));assert reader.call_count==2
            # Transaction verification intentionally bypasses the metadata cache.
            audit(root,use_cache=False);assert reader.call_count==3


def test_cached_runtime_flags_do_not_hide_duplicate_root_mods():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/'a.jar';path.write_bytes(jar('same'))
        audit(root,runtime_mods=[path])
        (root/'b.jar').write_bytes(jar('same'))
        assert any(i.code=='duplicate' for i in audit(root))


def test_parallel_updates_match_serial_and_ignore_disabled_mods():
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);versions=[]
        for i in range(12):
            key='mod'+str(i);data=jar(key);(folder/(key+'.jar')).write_bytes(data)
            versions.extend([release(key,data,date='2025-01-01'),release(key,jar(key,'2.0'),'2.0',date='2026-01-01')])
        (folder/'disabled.jar.disabled').write_bytes(b'not a jar')
        remote=Catalog(versions,{});remote.threads=1;serial=updates(remote,folder,'1.21.1','fabric')
        remote.threads=8;concurrent=updates(remote,folder,'1.21.1','fabric')
        assert concurrent==serial and len(concurrent[0])==12 and not concurrent[1]


def test_network_workers_receive_downloader_cancellation_context():
    class Remote(Downloader):
        def fetch_json(self,url):
            assert self._cancel_event() is cancel
            return dict(project_id=url,id=url)
        def post_json(self,url,payload):
            assert self._cancel_event() is cancel
            return {digest:dict(project_id=digest,id=digest) for digest in payload['hashes']}
    class Job:
        def emit(self,value):pass
    cancel=threading.Event();job=Job();job.cancel=cancel;remote=Remote()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for i in range(8):(root/(str(i)+'.jar')).write_bytes(jar('mod'+str(i)))
        found,unknown=identify(remote,root,job)
        assert len(found)==8 and not unknown
        assert remote._cancel_event() is None


def test_parallel_audit_matches_uncached_and_reports_every_file():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for i in range(12):(root/(str(i)+'.jar')).write_bytes(jar('mod'+str(i),depends={'missing':'*'}))
        (root/'broken.jar').write_bytes(b'broken')
        progress=[];expected=audit(root,use_cache=False)
        actual=audit(root,progress=lambda n,total:progress.append((n,total)))
        assert actual==expected and len(actual)==13
        assert progress==[(n,13) for n in range(1,14)]
