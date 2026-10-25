"""Queued task execution. Worker threads never access widgets or run GUI callbacks."""
import threading
import uuid
import time
from contextlib import nullcontext
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt


class Bus(QObject):
    completed = Signal(str, object, object)
    progress = Signal(str, object)


class Job(QRunnable):
    def __init__(self, key, bus, function, downloader=None):
        super().__init__()
        self.key, self.bus, self.function, self.downloader = key, bus, function, downloader
        self.cancel = threading.Event()
        self._progress_lock = threading.Lock()
        self._last_progress = 0.0
        self._transferred = 0
        self._last_transfer = 0.0

    def cancel_job(self):self.cancel.set()

    def transferred(self, size):
        # Parallel download workers share this job counter, never any widget.
        with self._progress_lock:
            self._transferred += size
            now=time.monotonic()
            if now-self._last_transfer<.1:return
            self._last_transfer=now
            self.bus.progress.emit(self.key,{'kind':'transfer','bytes':self._transferred,'at':now})

    def emit(self, value):
        if isinstance(value, tuple) and len(value) == 2 and all(isinstance(n, (int, float)) for n in value):
            with self._progress_lock:
                now = time.monotonic()
                if now - self._last_progress < .05 and value[0] != value[1]:
                    return
                self._last_progress = now
        self.bus.progress.emit(self.key, value)

    @Slot()
    def run(self):
        result=error=None
        try:
            with self.downloader.cancellable(self.cancel,self.transferred) if self.downloader else nullcontext():
                result = self.function(self)
        except Exception as exc:
            error=exc
        if self._transferred:
            self.bus.progress.emit(self.key,{'kind':'transfer','bytes':self._transferred,'at':time.monotonic()})
        self.bus.completed.emit(self.key,result,error)


class TaskManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.bus = Bus(self)
        self.jobs = {}
        self.tracked = {}
        self.bus.completed.connect(self._completed, Qt.ConnectionType.QueuedConnection)
        self.bus.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)

    def submit(self, function, done=None, failed=None, progress=None, downloader=None,*,title=None,library='',instance=''):
        key = uuid.uuid4().hex
        job = Job(key, self.bus, function, downloader)
        self.jobs[key] = (job, done, failed, progress)
        history=getattr(self.parent(),'task_history',None)
        if title and history:
            record=history.begin(title,library,instance);self.tracked[key]=(history,record);history.live[record['id']]=job
        self.pool.start(job)
        return job

    @Slot(str, object)
    def _progress(self, key, value):
        if key in self.tracked:
            history,record=self.tracked[key];history.progress(record,value)
        item = self.jobs.get(key)
        if item and item[3]:
            item[3](value)

    @Slot(str, object, object)
    def _completed(self, key, result, error):
        item = self.jobs.pop(key, None)
        tracked=self.tracked.pop(key,None)
        if item and tracked:
            history,record=tracked;history.finish(record,'cancelled' if item[0].cancel.is_set() else 'failed' if error else 'complete',str(error) if error else '')
        if item:
            callback = item[2] if error else item[1]
            if callback:
                callback(error if error else result)

    def cancel_all(self):
        for item in self.jobs.values():
            item[0].cancel.set()
