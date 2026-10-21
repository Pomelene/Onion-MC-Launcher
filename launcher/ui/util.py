# -*- coding: utf-8 -*-
"""界面辅助：后台任务、进度对话框、窗口居中。"""

from .dpi import px
import threading
import queue
from contextlib import nullcontext
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


def center(window: tk.Toplevel | tk.Tk, parent: Optional[tk.Misc] = None) -> None:
    """把窗口居中（相对父窗口）。"""
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if parent is not None and parent.winfo_exists():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"+{max(0, x)}+{max(0, y)}")


def run_async(widget: tk.Misc, task: Callable,
              on_success: Optional[Callable] = None,
              on_error: Optional[Callable] = None, downloader=None, cancel_event=None) -> None:
    """在后台线程执行 task()，完成后在主线程回调。"""

    result_queue = queue.Queue()
    pending = [None]

    def worker() -> None:
        try:
            with downloader.cancellable(cancel_event) if downloader is not None else nullcontext():
                result = task()
        except Exception as exc:  # noqa: BLE001
            result_queue.put((False, exc))
        else:
            result_queue.put((True, result))

    def deliver() -> None:
        pending[0] = None
        try:
            if not widget.winfo_exists():
                return
            ok, value = result_queue.get_nowait()
        except queue.Empty:
            pending[0] = widget.after(50, deliver)
            return
        except tk.TclError:
            return
        callback = on_success if ok else on_error
        if callback:
            callback(value)

    def destroyed(event):
        if event.widget is widget and pending[0] is not None:
            try:
                widget.after_cancel(pending[0])
            except tk.TclError:
                pass
            pending[0] = None

    widget.bind("<Destroy>", destroyed, add="+")
    pending[0] = widget.after(50, deliver)

    threading.Thread(target=worker, daemon=True).start()


class ProgressDialog(tk.Toplevel):
    """阻塞式进度对话框：显示当前阶段与百分比，可取消。"""

    def __init__(self, parent: tk.Misc, title: str = "请稍候", cancelable: bool = True):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.cancelled = False
        self.cancel_event = threading.Event()
        self._done = 0
        self._total = 0

        self.message_var = tk.StringVar(value="准备中……")
        ttk.Label(self, textvariable=self.message_var, width=44).pack(padx=px(16), pady=px((16, 6)))
        self.bar = ttk.Progressbar(self, mode="determinate", length=px(420), maximum=100)
        self.bar.pack(padx=px(16), pady=px(4))
        self.count_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.count_var).pack(pady=px((0, 6)))
        if cancelable:
            ttk.Button(self, text="取消", command=self._on_cancel).pack(pady=px((0, 12)))
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.grab_set()
        center(self, parent)

    def _on_cancel(self) -> None:
        self.cancelled = True
        self.cancel_event.set()
        self.message_var.set("正在取消……")

    def set_message(self, text: str) -> None:
        if self.winfo_exists():
            self.message_var.set(text)

    def set_progress(self, done: int, total: int) -> None:
        if not self.winfo_exists():
            return
        self._done, self._total = done, total
        pct = int(done * 100 / total) if total else 0
        self.bar["value"] = pct
        self.count_var.set(f"{done} / {total}（{pct}%）" if total else "")

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
