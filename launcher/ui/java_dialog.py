# -*- coding: utf-8 -*-
"""Java 管理：列出本机发现的 Java，并可下载 Mojang 官方运行时。"""

from .dpi import px, geometry
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from ..java import download_java, find_all_java, list_downloadable
from .util import center
from .widgets import FlatButton


class JavaDialog(tk.Toplevel):
    """Java 运行时管理窗口。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.p = app.palette
        self.title("Java 运行时")
        self.configure(bg=self.p["bg"])
        self.transient(master)
        self.geometry(geometry("720x460"))

        header = tk.Frame(self, bg=self.p["bg"])
        header.pack(fill="x", padx=px(16), pady=px((12, 4)))
        tk.Label(header, text="已发现的 Java", bg=self.p["bg"], fg=self.p["fg"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        FlatButton(header, self.p, "重新检测", command=self._reload).pack(side="right")

        self.detected = tk.Frame(self, bg=self.p["bg"])
        self.detected.pack(fill="both", expand=True, padx=px(16))

        tk.Label(self, text="可下载的官方运行时", bg=self.p["bg"], fg=self.p["fg"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=px(16), pady=px((10, 4)))
        self.available = tk.Frame(self, bg=self.p["bg"])
        self.available.pack(fill="both", expand=True, padx=px(16))

        self.status = tk.Label(self, text="", bg=self.p["bg"], fg=self.p["muted"],
                               font=("Microsoft YaHei UI", 9))
        self.status.pack(anchor="w", padx=px(16), pady=px((4, 10)))

        self._queue: queue.Queue = queue.Queue()
        self._reload()
        self.status.configure(text="正在获取可下载列表……")
        threading.Thread(target=self._fetch_available, daemon=True).start()
        self.after(120, self._poll_queue)
        self.grab_set()
        center(self)

    # ------------------------------------------------------------ 列表

    def _clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _reload(self):
        self._clear(self.detected)
        infos = find_all_java()
        if not infos:
            tk.Label(self.detected, text="未发现 Java。可以下载下方官方运行时。",
                     bg=self.p["bg"], fg=self.p["muted"]).pack(anchor="w", pady=px(4))
            return
        for info in infos:
            row = tk.Frame(self.detected, bg=self.p["surface"])
            row.pack(fill="x", pady=px(2))
            tk.Label(row, text=f"Java {info.major}", width=10, anchor="w",
                     bg=self.p["surface"], fg=self.p["accent"],
                     font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=px(6))
            tk.Label(row, text=str(info.path), anchor="w", bg=self.p["surface"],
                     fg=self.p["fg"], font=("Consolas", 9)).pack(side="left", padx=px(6))
            FlatButton(row, self.p, "设为全局",
                       command=lambda i=info: self._use_global(i)).pack(side="right", padx=px(6), pady=px(3))

    def _fetch_available(self):
        try:
            items = list_downloadable(self.app.repo.downloader)
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("status", f"获取可下载列表失败：{exc}"))
            return
        self._queue.put(("items", items))

    def _poll_queue(self):
        """主线程轮询工作线程的结果（Tk 的 after 不能跨线程调用）。"""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                elif kind == "items":
                    self._render_available(payload)
                elif kind == "downloaded":
                    self._on_downloaded(payload)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(120, self._poll_queue)

    def _render_available(self, items):
        self._clear(self.available)
        self.status.configure(text="")
        for item in items:
            row = tk.Frame(self.available, bg=self.p["surface"])
            row.pack(fill="x", pady=px(2))
            tk.Label(row, text=f"Java {item['major']}", width=10, anchor="w",
                     bg=self.p["surface"], fg=self.p["fg"],
                     font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=px(6))
            tk.Label(row, text=item.get("name", ""), anchor="w", bg=self.p["surface"],
                     fg=self.p["muted"]).pack(side="left", padx=px(6))
            FlatButton(row, self.p, "下载",
                       command=lambda i=item: self._download(i)).pack(side="right", padx=px(6), pady=px(3))

    # ------------------------------------------------------------ 操作

    def _use_global(self, info):
        self.app.config_obj.set("java_path", str(info.path))
        self.app.config_obj.save()
        self.app.log(f"全局 Java 已设为 {info.major}：{info.path}")
        self.status.configure(text=f"已设为全局：Java {info.major}")

    def _download(self, item):
        major = int(item["major"])
        self.status.configure(text=f"正在下载 Java {major}……")

        def worker():
            def stage(text):
                self._queue.put(("status", text))

            try:
                info = download_java(major, self.app.repo.downloader, stage)
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("status", f"下载失败：{exc}"))
                return
            self._queue.put(("downloaded", info))

        threading.Thread(target=worker, daemon=True).start()

    def _on_downloaded(self, info):
        if info is None:
            self.status.configure(text="下载失败：没有可用的官方运行时")
            return
        self.app.config_obj.set("java_path", str(info.path))
        self.app.config_obj.save()
        self.status.configure(text=f"已下载并设为全局：Java {info.major}")
        self.app.log(f"已下载 Java {info.major}：{info.path}")
        self._reload()