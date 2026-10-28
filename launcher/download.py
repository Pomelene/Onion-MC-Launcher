# -*- coding: utf-8 -*-
"""并发下载引擎。

特性：
- 多线程并发下载
- 自动重试（指数退避）
- SHA-1 / 大小校验，本地文件已满足要求则跳过
- 进度回调
- JSON / 文本请求封装
"""

import hashlib
import json
import io
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional
from .network import validate_url,SafeRedirectHandler,https_handler
from .paths import LAUNCHER_VERSION

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
USER_AGENT = f"Onion Minecraft Launcher/{LAUNCHER_VERSION} (Minecraft Launcher)"


class DownloadError(Exception):
    """下载失败（含校验失败）。"""

    def __init__(self,message,http_status=None):
        super().__init__(message);self.http_status=http_status


class DownloadCancelled(DownloadError):
    """用户主动取消了下载。"""


def sha1_of(path: Path) -> Optional[str]:
    """计算文件 SHA-1；文件不存在或读取失败返回 None。"""
    try:
        with open(path, "rb") as f:
            return hashlib.file_digest(f, 'sha1').hexdigest()
    except OSError:
        return None


@dataclass
class DownloadJob:
    """一个待下载文件。"""

    url: str
    path: Path
    sha1: Optional[str] = None
    size: Optional[int] = None
    name: Optional[str] = None  # 进度显示用
    cancel_event: Optional[threading.Event] = None  # 协作式取消
    error: str = ""
    fallback_urls: tuple[str, ...] = ()
    sha256: Optional[str] = None
    force: bool = False
    max_size: int = 8*1024**3

    def __str__(self) -> str:
        return self.name or self.path.name


class Downloader:
    """多线程下载器。"""

    def __init__(self, threads: int = 8, retries: int = DEFAULT_RETRIES,
                 timeout: int = DEFAULT_TIMEOUT, proxy: Optional[str] = None,
                 speed_limit: int = 0, *, use_system_proxy: bool = True):
        self.threads = max(1, threads)
        self.retries = max(1, retries)
        self.timeout = timeout
        self.proxy = proxy
        self.use_system_proxy = use_system_proxy
        self.speed_limit = max(0, int(speed_limit))  # KB/s，0 表示不限
        self._local = threading.local()
        self._rate_lock = threading.Lock()
        self._rate_next = 0.0
        self.write_guard = None

    @contextmanager
    def cancellable(self, event, on_bytes=None):
        previous = getattr(self._local, "cancel_event", None)
        previous_bytes = getattr(self._local, "on_bytes", None)
        self._local.cancel_event = event
        self._local.on_bytes = on_bytes if on_bytes is not None else previous_bytes
        try:
            yield
        finally:
            self._local.cancel_event = previous
            self._local.on_bytes = previous_bytes

    def _transferred(self, size):
        callback = getattr(self._local, 'on_bytes', None)
        if callback:callback(size)

    def _cancel_event(self):
        return getattr(self._local, "cancel_event", None)

    def _opener(self) -> urllib.request.OpenerDirector:
        handlers: list = [urllib.request.HTTPHandler(), https_handler(),SafeRedirectHandler()]
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler(
                {"http": self.proxy, "https": self.proxy}))
        elif not self.use_system_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener(*handlers)

    # ---------- 简单请求 ----------

    def fetch(self, url: str, binary: bool = False, headers: Optional[dict] = None, *, data=None, method=None):
        """GET 请求并返回 bytes（binary=True）或解码后的 str。失败自动重试。

        headers 用于需要鉴权的接口（如 CurseForge 的 x-api-key）。
        """
        validate_url(url)
        request_headers = {"User-Agent": USER_AGENT}
        if headers:
            request_headers.update(headers)
        last: Optional[Exception] = None
        request_data=data
        for _ in range(self.retries):
            event = self._cancel_event()
            if event is not None and event.is_set():
                raise DownloadCancelled("已取消请求")
            try:
                req = urllib.request.Request(url, headers=request_headers,data=request_data,method=method)
                with self._opener().open(req, timeout=self.timeout) as resp:
                    reader=getattr(resp,'read1',resp.read);output=io.BytesIO();received=0
                    while True:
                        if event is not None and event.is_set():raise DownloadCancelled('已取消请求')
                        block=reader(min(256*1024,32*1024**2+1-received))
                        if not block:break
                        received+=len(block)
                        if received>32*1024**2:raise DownloadError('响应内容超过安全上限')
                        output.write(block);self._transferred(len(block))
                    content=output.getvalue()
                return content if binary else content.decode("utf-8")
            except DownloadCancelled:raise
            except Exception as e:  # noqa: BLE001
                last = e
                if isinstance(e,urllib.error.HTTPError) and e.code==404:break
        raise DownloadError(f"网络请求失败（{type(last).__name__}），请检查网络及服务状态",getattr(last,'code',None)) from None

    def fetch_json(self, url: str, headers: Optional[dict] = None):
        return json.loads(self.fetch(url, headers=headers))

    def post_json(self,url,payload):
        body=json.dumps(payload,separators=(',',':')).encode('utf-8')
        if len(body)>1024*1024:raise ValueError('请求内容超过安全上限')
        return json.loads(self.fetch(url,headers={'Content-Type':'application/json','Accept':'application/json'},data=body,method='POST'))

    # ---------- 单文件下载 ----------

    def _check_cancel(self, job: DownloadJob) -> None:
        if job.cancel_event is not None and job.cancel_event.is_set():
            raise DownloadCancelled(f"已取消下载: {job}")

    def _throttle(self, nbytes: int, cancel_event=None) -> None:
        """粗略限速：按读取字节数休眠（speed_limit 单位为 KB/s）。"""
        if not self.speed_limit:
            return
        with self._rate_lock:
            now = time.monotonic()
            self._rate_next = max(now, self._rate_next) + nbytes / (self.speed_limit * 1024)
            delay = self._rate_next - now
        if cancel_event is not None:
            if cancel_event.wait(delay):
                raise DownloadCancelled("已取消下载")
        else:
            time.sleep(delay)

    def download_one(self, job: DownloadJob,
                     progress: Optional[Callable[[int, int], None]] = None) -> bool:
        """下载单个文件；已存在且校验通过则跳过。返回是否成功。

        支持：.part 断点续传（Range）、协作式取消、限速、SHA-1/大小校验、原子落盘。
        """
        path = job.path
        validate_url(job.url)
        if job.cancel_event is None:
            job.cancel_event = self._cancel_event()
        self._check_cancel(job)
        if self.write_guard:
            self.write_guard(path)
            self.write_guard(path.with_name(path.name + ".part"))
        if type(job.max_size) is not int or not 0<job.max_size<=8*1024**3:raise DownloadError('下载大小限制无效')
        if job.size is not None and (not isinstance(job.size,int) or isinstance(job.size,bool) or job.size<0 or job.size>job.max_size):
            raise DownloadError('下载文件大小超出安全范围')
        for expected,length in ((job.sha1,40),(job.sha256,64)):
            if expected and (len(expected)!=length or any(c not in '0123456789abcdefABCDEF' for c in expected)):
                raise DownloadError('下载摘要格式无效')
        if not job.force and job.size is not None and path.exists() and path.stat().st_size == job.size and not job.sha1 and not job.sha256:
            return True
        if not job.force and (job.sha1 or job.sha256) and (not path.exists() or path.stat().st_size<=job.max_size) and self._hash_valid(path,job):
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        if job.force:tmp.unlink(missing_ok=True)
        if tmp.exists() and tmp.stat().st_size>job.max_size:tmp.unlink()
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                self._check_cancel(job)
                offset = tmp.stat().st_size if tmp.exists() else 0
                headers = {"User-Agent": USER_AGENT}
                if offset > 0:
                    headers["Range"] = f"bytes={offset}-"
                req = urllib.request.Request(job.url, headers=headers)
                with self._opener().open(req, timeout=self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    resume = (status == 206 and offset > 0)
                    total = int(resp.headers.get("Content-Length") or 0)
                    done = offset if resume else 0
                    if status==206:
                        import re
                        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',resp.headers.get('Content-Range',''))
                        if not resume or not match or int(match[1])!=offset or int(match[2])<offset or int(match[2])+1!=int(match[3]) or (job.size is not None and int(match[3])!=job.size) or (total and total!=int(match[2])-offset+1):
                            tmp.unlink(missing_ok=True)
                            raise DownloadError('服务器返回的续传范围无效')
                        total=int(match[3])
                    if total>(job.size if job.size is not None else job.max_size):raise DownloadError('下载内容超过声明大小或安全上限')
                    digests={name:hashlib.new(name) for name,expected in (('sha1',job.sha1),('sha256',job.sha256)) if expected}
                    if resume and digests:
                        with tmp.open('rb') as existing:
                            for block in iter(lambda:existing.read(256*1024),b''):
                                self._check_cancel(job)
                                for digest in digests.values():digest.update(block)
                    with open(tmp, "ab" if resume else "wb") as f:
                        reader=getattr(resp,'read1',resp.read)
                        while True:
                            self._check_cancel(job)
                            chunk = reader(256*1024)
                            if not chunk:
                                break
                            if done+len(chunk)>(job.size if job.size is not None else job.max_size):
                                raise DownloadError('下载内容超过声明大小或安全上限')
                            f.write(chunk)
                            for digest in digests.values():digest.update(chunk)
                            self._transferred(len(chunk))
                            done += len(chunk)
                            if progress and total:
                                progress(done, total)
                            self._throttle(len(chunk), job.cancel_event)
                if total and done!=total:raise DownloadError('下载连接提前结束')
                if any(digest.hexdigest()!=getattr(job,name).lower() for name,digest in digests.items()):
                    tmp.unlink(missing_ok=True)
                    raise DownloadError('文件摘要校验失败')
                if job.size is not None and tmp.stat().st_size != job.size:
                    tmp.unlink(missing_ok=True)
                    raise DownloadError('文件大小不符')
                from .safety import backup_file
                self._check_cancel(job)
                backup_file(path)
                from .storage import _replace
                _replace(tmp,path)
                return True
            except DownloadCancelled:
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt+1<self.retries:
                    delay=.5*(attempt+1)
                    if job.cancel_event is not None:
                        if job.cancel_event.wait(delay):raise DownloadCancelled('已取消下载')
                    else:time.sleep(delay)
        remaining = tuple(u for u in job.fallback_urls if u != job.url)
        if remaining:
            tmp.unlink(missing_ok=True)
            return self.download_one(replace(job, url=remaining[0], fallback_urls=remaining[1:]), progress)
        raise DownloadError(f"下载失败（{type(last).__name__}），请检查网络及文件完整性") from None

    @staticmethod
    def _hash_valid(path,job):
        if not path.is_file():return False
        if job.size is not None and path.stat().st_size!=job.size:return False
        digests={name:hashlib.new(name) for name,expected in (('sha1',job.sha1),('sha256',job.sha256)) if expected}
        with path.open('rb') as source:
            for block in iter(lambda:source.read(256*1024),b''):
                if job.cancel_event is not None and job.cancel_event.is_set():raise DownloadCancelled('已取消校验')
                for digest in digests.values():digest.update(block)
        return all(digest.hexdigest()==getattr(job,name).lower() for name,digest in digests.items())

    # ---------- 批量并发下载 ----------

    def download_many(self, jobs: list,
                      on_progress: Optional[Callable[[int, int], None]] = None,
                      on_done: Optional[Callable[[object, bool], None]] = None,
                      cancel_event: Optional[threading.Event] = None
                      ) -> tuple[list, list]:
        """并发下载一组文件。on_progress(已完成数, 总数)；on_done(job, 是否成功)。

        cancel_event 可整体取消；返回 (成功列表, 失败列表)。
        """
        ok: list = []
        failed: list = []
        total = len(jobs)
        done = 0
        lock = threading.Lock()
        cancel_event = cancel_event if cancel_event is not None else self._cancel_event()
        on_bytes = getattr(self._local, 'on_bytes', None)

        def worker(job) -> None:
            nonlocal done
            if cancel_event is not None and job.cancel_event is None:
                job.cancel_event = cancel_event
            success=False
            try:
                with self.cancellable(cancel_event,on_bytes):
                    self.download_one(job)
                success=True
            except DownloadCancelled:
                pass
            except Exception as e:  # noqa: BLE001
                job.error=str(e)
            with lock:
                done+=1
                (ok if success else failed).append(job)
                if on_progress:on_progress(done,total)
                if on_done:on_done(job,success)

        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            pending=set();iterator=iter(jobs)
            while True:
                while len(pending)<self.threads*2:
                    job=next(iterator,None)
                    if job is None:break
                    pending.add(pool.submit(worker,job))
                if not pending:break
                finished,pending=wait(pending,return_when=FIRST_COMPLETED)
                for future in finished:future.result()
        return ok, failed
