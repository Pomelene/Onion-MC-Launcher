# -*- coding: utf-8 -*-
"""统一任务队列。

所有长任务（安装/下载/导入/导出）都提交到 TaskQueue 在后台线程执行，
UI 只通过 on_update / on_finish 回调消费状态变化，避免阻塞主线程。
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional


class Task:
    """一个后台任务；work 为 callable(task)，可在执行中调用 task.report() 更新进度，
    并通过 task.cancel_event 检查取消。"""

    def __init__(self, name: str, work: Callable[["Task"], Any],
                 cancel_event: Optional[threading.Event] = None):
        self.id: str = uuid.uuid4().hex[:12]
        self.name = name
        self.work = work
        self.status = "pending"   # pending | running | done | failed | cancelled
        self.message = ""
        self.progress = 0
        self.total = 0
        self.error: Optional[str] = None
        self.result: Any = None
        self.cancel_event = cancel_event or threading.Event()

    def report(self, message: Optional[str] = None, progress: Optional[int] = None,
               total: Optional[int] = None) -> None:
        if message is not None:
            self.message = message
        if progress is not None:
            self.progress = progress
        if total is not None:
            self.total = total

    def cancel(self) -> None:
        self.cancel_event.set()
        self.message = "正在取消…"

    @property
    def done(self) -> bool:
        return self.status in ("done", "failed", "cancelled")

    @property
    def percent(self) -> int:
        return int(self.progress * 100 / self.total) if self.total else 0

    def snapshot(self) -> dict:
        return {
            "id": self.id, "name": self.name, "status": self.status,
            "message": self.message, "progress": self.progress,
            "total": self.total, "error": self.error,
        }


class TaskQueue:
    """有限并发地执行任务，回调在后台线程触发（UI 侧需自行调度到主线程）。"""

    def __init__(self, max_workers: int = 2,
                 on_update: Optional[Callable[[Task], None]] = None,
                 on_finish: Optional[Callable[[Task], None]] = None):
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._order: list[str] = []
        self.on_update = on_update
        self.on_finish = on_finish

    def submit(self, task: Task) -> Task:
        with self._lock:
            self._tasks[task.id] = task
            self._order.append(task.id)
        self._executor.submit(self._run, task)
        return task

    def _run(self, task: Task) -> None:
        with self._lock:
            task.status = "running"
        self._emit(self.on_update, task)
        try:
            task.result = task.work(task)
            with self._lock:
                task.status = "cancelled" if task.cancel_event.is_set() else "done"
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                task.status = "cancelled" if task.cancel_event.is_set() else "failed"
                task.error = str(exc)
        self._emit(self.on_finish, task)

    @staticmethod
    def _emit(cb, task: Task) -> None:
        if cb is None:
            return
        try:
            cb(task)
        except Exception:  # noqa: BLE001
            pass

    def snapshot(self) -> list[Task]:
        with self._lock:
            return [self._tasks[i] for i in self._order if i in self._tasks]

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_all(self) -> None:
        for task in self.snapshot():
            if not task.done:
                task.cancel()

    def active_count(self) -> int:
        return sum(1 for t in self.snapshot() if not t.done)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)
