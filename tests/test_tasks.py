# -*- coding: utf-8 -*-
import threading

from launcher.tasks import Task, TaskQueue


def test_task_success():
    q = TaskQueue(max_workers=2)
    t = Task("add", lambda task: 42)
    q.submit(t)
    q.shutdown(wait=True)
    assert t.status == "done" and t.result == 42


def test_task_failure():
    def boom(task):
        raise RuntimeError("boom")
    q = TaskQueue(max_workers=1)
    t = Task("fail", boom)
    q.submit(t)
    q.shutdown(wait=True)
    assert t.status == "failed" and "boom" in (t.error or "")


def test_report_and_percent():
    q = TaskQueue(1)
    t = Task("report", lambda task: (task.report("一半", 5, 10), 1)[1])
    q.submit(t)
    q.shutdown(wait=True)
    assert t.message == "一半" and t.percent == 50


def test_cancel_marks_cancelled():
    ev = threading.Event()
    ev.set()
    q = TaskQueue(1)
    t = Task("c", lambda task: 42, cancel_event=ev)
    q.submit(t)
    q.shutdown(wait=True)
    assert t.status == "cancelled"


def test_cancel_all():
    import time
    def slow(task):
        for _ in range(50):
            if task.cancel_event.is_set():
                raise InterruptedError()
            time.sleep(0.05)
        return 1
    q = TaskQueue(2)
    q.submit(Task("a", slow))
    q.submit(Task("b", slow))
    time.sleep(0.05)
    q.cancel_all()
    q.shutdown(wait=True)
    for t in q.snapshot():
        assert t.status == "cancelled"
