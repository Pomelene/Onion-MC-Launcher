# -*- coding: utf-8 -*-
import hashlib
import threading

from launcher.download import (DownloadCancelled, DownloadError, DownloadJob,
                               Downloader)
from tests.harness import FakeServer, temp_workspace


def test_transfer_bytes_propagate_to_parallel_workers_and_skip_cached_files():
    payload=b'a'*140000;server=FakeServer({'/one':payload,'/two':payload}).start()
    try:
        with temp_workspace() as root:
            downloader=Downloader(retries=1);received=[];event=threading.Event()
            jobs=[DownloadJob(server.url('/'+name),root/name,size=len(payload)) for name in ('one','two')]
            with downloader.cancellable(event,received.append):
                ok,failed=downloader.download_many(jobs)
            assert len(ok)==2 and not failed and sum(received)==len(payload)*2
            received.clear()
            with downloader.cancellable(event,received.append):
                downloader.download_many(jobs)
            assert received==[], 'Local cache checks must not count as network bytes'
            # Context exit cannot leak telemetry into later unrelated operations.
            downloader.fetch(server.url('/one'),binary=True);assert received==[]
    finally:server.stop()


def test_download_ok():
    data = b"hello world"
    srv = FakeServer({"/f": data}).start()
    try:
        with temp_workspace() as d:
            dl = Downloader(retries=1)
            job = DownloadJob(srv.url("/f"), d / "out.bin",
                              sha1=hashlib.sha1(data).hexdigest(), size=len(data))
            assert dl.download_one(job) is True
            assert (d / "out.bin").read_bytes() == data
            assert not (d / "out.bin.part").exists()
    finally:
        srv.stop()


def test_sha1_mismatch():
    srv = FakeServer({"/f": b"corrupt"}).start()
    try:
        with temp_workspace() as d:
            dl = Downloader(retries=1)
            job = DownloadJob(srv.url("/f"), d / "o.bin", sha1="0" * 40)
            try:
                dl.download_one(job)
                assert False, "应当抛出 DownloadError"
            except DownloadError:
                pass
            assert not (d / "o.bin").exists()
    finally:
        srv.stop()


def test_size_mismatch():
    srv = FakeServer({"/f": b"abc"}).start()
    try:
        with temp_workspace() as d:
            dl = Downloader(retries=1)
            job = DownloadJob(srv.url("/f"), d / "o.bin", size=999)
            try:
                dl.download_one(job)
                assert False
            except DownloadError:
                pass
    finally:
        srv.stop()


def test_cancel_before_start():
    with temp_workspace() as d:
        dl = Downloader(retries=1)
        ev = threading.Event()
        ev.set()
        job = DownloadJob("http://127.0.0.1:1/nope", d / "x.bin", cancel_event=ev)
        try:
            dl.download_one(job)
            assert False
        except DownloadCancelled:
            pass


def test_resume_from_part():
    data = b"0123456789"
    srv = FakeServer({"/f": data}).start()
    try:
        with temp_workspace() as d:
            dl = Downloader(retries=1)
            job = DownloadJob(srv.url("/f"), d / "r.bin",
                              sha1=hashlib.sha1(data).hexdigest())
            (d / "r.bin.part").write_bytes(b"01234")
            dl.download_one(job)
            assert (d / "r.bin").read_bytes() == data
            assert srv.ranges, "续传应发送 Range 请求"
    finally:
        srv.stop()


def test_existing_valid_skips():
    data = b"skip-me"
    with temp_workspace() as d:
        dl = Downloader(retries=1)
        target = d / "e.bin"
        target.write_bytes(data)
        job = DownloadJob("http://127.0.0.1:1/nope", target, sha1=hashlib.sha1(data).hexdigest())
        assert dl.download_one(job) is True  # 不联网直接通过
