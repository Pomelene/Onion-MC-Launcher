"""Bounded, cancellable read-only work with deterministic result ordering."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from .download import DownloadCancelled


def ordered_parallel(work, items, *, workers=4, cancel=None, progress=None, slots=None):
    items=list(items)

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled('检查已取消')

    def run(item):
        if slots is None:
            check_cancel();return work(item)
        while not slots.acquire(timeout=.05):check_cancel()
        try:
            check_cancel();return work(item)
        finally:slots.release()

    check_cancel()
    if not items:
        return []
    workers=max(1,min(int(workers),8,len(items)))
    results=[None]*len(items)
    if workers==1:
        for index,item in enumerate(items):
            check_cancel();results[index]=run(item);check_cancel()
            if progress:progress(index+1,len(items))
        return results
    pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='onion-check')
    pending={};next_index=0;completed=0;success=False
    try:
        while next_index<len(items) or pending:
            check_cancel()
            # Keep only one work item per worker queued, even for huge mod lists.
            while next_index<len(items) and len(pending)<workers:
                check_cancel()
                pending[pool.submit(run,items[next_index])]=next_index
                next_index+=1
            ready,_=wait(pending,timeout=.05,return_when=FIRST_COMPLETED)
            for future in ready:
                index=pending.pop(future);results[index]=future.result();completed+=1
                check_cancel()
                if progress:progress(completed,len(items))
        success=True
        return results
    finally:
        # Cancellation stops scheduling immediately; already-running I/O observes
        # the same cancellation event instead of blocking the UI's worker.
        pool.shutdown(wait=success,cancel_futures=True)
