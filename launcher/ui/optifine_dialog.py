# -*- coding: utf-8 -*-
"""OptiFine 安装窗口：查询某原版版本可用的 OptiFine，并调用无界面安装。"""

from .dpi import px, geometry
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from ..install.optifine import install as install_optifine, list_editions
from ..java import pick_java
from .util import center
from .widgets import FlatButton


class OptiFineDialog(tk.Toplevel):
    """OptiFine 版本选择与安装。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.p = app.palette
        self.items: list[dict] = []
        self._queue: queue.Queue = queue.Queue()
        self.title("安装 OptiFine")
        self.configure(bg=self.p["bg"])
        self.transient(master)
        self.geometry(geometry("640x480"))

        top = tk.Frame(self, bg=self.p["bg"])
        top.pack(fill="x", padx=px(16), pady=px((14, 6)))
        tk.Label(top, text="原版版本", bg=self.p["bg"], fg=self.p["fg"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.version_var = tk.StringVar(value=self.app.selected_version or "1.20.4")
        entry = tk.Entry(top, textvariable=self.version_var, width=14,
                         bg=self.p["surface"], fg=self.p["fg"],
                         insertbackground=self.p["fg"], relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=self.p["border"],
                         highlightcolor=self.p["border"])
        entry.pack(side="left", padx=px(8))
        FlatButton(top, self.p, "查询版本", command=self._query).pack(side="left")
        tk.Label(top, text="（稳定版优先，预览版标 *）", bg=self.p["bg"],
                 fg=self.p["muted"], font=("Microsoft YaHei UI", 9)).pack(side="left", padx=px(8))

        body = tk.Frame(self, bg=self.p["bg"])
        body.pack(fill="both", expand=True, padx=px(16))
        self.listbox = tk.Listbox(body, bg=self.p["surface"], fg=self.p["fg"],
                                  selectbackground=self.p["accent"],
                                  selectforeground=self.p["accent_fg"],
                                  relief="flat", bd=0, highlightthickness=0,
                                  font=("Consolas", 10), activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(body, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)

        bottom = tk.Frame(self, bg=self.p["bg"])
        bottom.pack(fill="x", padx=px(16), pady=px(10))
        self.install_btn = FlatButton(bottom, self.p, "安装选中版本",
                                      command=self._install, kind="accent")
        self.install_btn.pack(side="right")
        self.status = tk.Label(bottom, text="先查询，再选择要安装的版本",
                               bg=self.p["bg"], fg=self.p["muted"],
                               font=("Microsoft YaHei UI", 9), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

        self.after(120, self._poll)
        self._query()
        self.grab_set()
        center(self)

    # ------------------------------------------------------------ 事件

    def _query(self):
        version = self.version_var.get().strip()
        if not version:
            self.status.configure(text="请输入原版版本号")
            return
        self.status.configure(text=f"正在查询 {version} 的 OptiFine……")

        def worker():
            try:
                self._queue.put(("items", list_editions(self.app.repo.downloader, version)))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", f"查询失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _install(self):
        selected = self.listbox.curselection()
        if not selected:
            self.status.configure(text="请先在列表里选择一个版本")
            return
        item = self.items[selected[0]]
        version = self.version_var.get().strip()
        self.install_btn.configure(state="disabled")
        self.status.configure(text=f"准备安装 OptiFine {item['label']}……")

        def worker():
            try:
                rv = self.app.repo.resolver.resolve(version)
                required = max(8, rv.java_major or 8)
                java = pick_java(required)
                if not java:
                    raise RuntimeError(f"没有找到 Java {required}+")
                vid = install_optifine(
                    self.app.repo, version, item, java_path=str(java.path),
                    on_stage=lambda text: self._queue.put(("status", text)))
                self._queue.put(("done", vid))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("error", f"安装失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "items":
                    self._render(payload)
                elif kind == "status":
                    self.status.configure(text=payload)
                elif kind == "done":
                    self._done(payload)
                elif kind == "error":
                    self.install_btn.configure(state="normal")
                    self.status.configure(text=payload)
                    messagebox.showerror("OptiFine", payload, parent=self)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(120, self._poll)

    def _render(self, items: list[dict]) -> None:
        self.items = items
        self.listbox.delete(0, "end")
        for item in items:
            mark = " *" if item["preview"] else "  "
            forge = f"  Forge {item['forge']}" if item["forge"] and item["forge"] != "Forge N/A" else ""
            self.listbox.insert("end", f"{item['label']:<18}{mark}{forge}")
        if items:
            self.listbox.selection_set(0)
            self.status.configure(text=f"共 {len(items)} 个版本，选择后点安装")
        else:
            self.status.configure(text="没有找到可用版本（检查版本号是否正确）")

    def _done(self, vid: str) -> None:
        self.install_btn.configure(state="normal")
        self.status.configure(text=f"安装完成：{vid}")
        self.app.log(f"OptiFine 安装完成：{vid}")
        page = self.app.pages.get("versions")
        if page is not None and hasattr(page, "refresh"):
            page.refresh()
        messagebox.showinfo("OptiFine", f"安装完成：{vid}\n\n已在版本列表中，可直接启动。",
                            parent=self)