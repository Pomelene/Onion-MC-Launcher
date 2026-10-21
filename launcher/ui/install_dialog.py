# -*- coding: utf-8 -*-
"""安装版本对话框：原版与各类模组加载器。"""

from .dpi import px, geometry
import tkinter as tk
from tkinter import messagebox, ttk

from ..install.fabric import install_loader, list_loaders
from .util import ProgressDialog, center, run_async

#: 加载器选项：key -> 显示名
LOADERS = [
    ("vanilla", "原版"),
    ("fabric", "Fabric"),
    ("quilt", "Quilt"),
    ("forge", "Forge"),
    ("neoforge", "NeoForge"),
]


class InstallDialog(tk.Toplevel):
    """选择游戏版本与加载器并安装。"""

    def __init__(self, parent, repo, on_installed):
        super().__init__(parent)
        self.repo = repo
        self.on_installed = on_installed
        self.title("安装新版本")
        self.geometry(geometry("620x520"))
        self.transient(parent)
        self.grab_set()

        self.loader_var = tk.StringVar(value="vanilla")
        self.loader_version_var = tk.StringVar(value="最新")
        self.search_var = tk.StringVar()
        self._entries = []
        self._versions = []

        self._build()
        center(self, parent)
        self._load_manifest()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="加载器：").pack(side="left")
        for key, label in LOADERS:
            ttk.Radiobutton(top, text=label, value=key, variable=self.loader_var,
                            command=self._on_loader_changed).pack(side="left", padx=px(2))

        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill="both", expand=True)
        ttk.Label(mid, text="搜索版本：").pack(anchor="w")
        search = ttk.Entry(mid, textvariable=self.search_var)
        search.pack(fill="x", pady=px((2, 6)))
        search.bind("<KeyRelease>", lambda e: self._apply_filter())

        list_frame = ttk.Frame(mid)
        list_frame.pack(fill="both", expand=True)
        self.version_list = tk.Listbox(list_frame, exportselection=False)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.version_list.yview)
        self.version_list.configure(yscrollcommand=sb.set)
        self.version_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.version_list.bind("<<ListboxSelect>>", lambda e: self._on_version_selected())

        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")
        ttk.Label(bottom, text="加载器版本：").pack(side="left")
        self.loader_box = ttk.Combobox(bottom, textvariable=self.loader_version_var,
                                       state="disabled", width=24)
        self.loader_box.pack(side="left", padx=px(4))
        self.install_btn = ttk.Button(bottom, text="安装", command=self._install)
        self.install_btn.pack(side="right")
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right", padx=px(6))
        self.status_var = tk.StringVar(value="正在获取版本清单……")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0)).pack(anchor="w")

    # ---------- 数据加载 ----------

    def _load_manifest(self) -> None:
        def task():
            return self.repo.fetch_manifest().snapshot_versions()

        def done(versions):
            self._entries = versions
            self.status_var.set(f"共 {len(versions)} 个版本")
            self._apply_filter()

        def failed(exc):
            self.status_var.set(f"获取版本清单失败：{exc}")
            messagebox.showerror("错误", f"获取版本清单失败：\n{exc}", parent=self)

        run_async(self, task, on_success=done, on_error=failed)

    def _apply_filter(self) -> None:
        keyword = self.search_var.get().strip().lower()
        self.version_list.delete(0, "end")
        self._versions = [v for v in self._entries
                          if not keyword or keyword in v.id.lower()]
        for v in self._versions:
            tag = "正式版" if v.type == "release" else v.type
            self.version_list.insert("end", f"{v.id}    [{tag}]")

    def _on_loader_changed(self) -> None:
        is_loader = self.loader_var.get() != "vanilla"
        self.loader_box.configure(state="readonly" if is_loader else "disabled")
        self.loader_version_var.set("最新")
        if is_loader:
            self._load_loader_versions()

    def _on_version_selected(self) -> None:
        if self.loader_var.get() != "vanilla":
            self._load_loader_versions()

    def _selected_game(self) -> str:
        sel = self.version_list.curselection()
        if not sel:
            return ""
        return self._versions[sel[0]].id

    def _load_loader_versions(self) -> None:
        game = self._selected_game()
        kind = self.loader_var.get()
        if not game or kind == "vanilla":
            return
        self.loader_version_var.set("加载中……")

        if kind in ("forge", "neoforge"):
            from ..install.forge import list_versions

            def task():
                return list_versions(self.repo, kind, game)

            def done(versions):
                values = ["最新"] + [v for v in versions[:40]]
                self.loader_box.configure(values=values)
                self.loader_version_var.set("最新")

            run_async(self, task, on_success=done,
                      on_error=lambda exc: self.loader_version_var.set("获取失败"))
            return

        def task():
            return list_loaders(self.repo.downloader, kind, game)

        def done(entries):
            versions = [(e.get("loader") or {}).get("version", "") for e in entries]
            stable = [(e.get("loader") or {}).get("version", "") for e in entries
                      if (e.get("loader") or {}).get("stable")]
            values = ["最新"] + versions[:40]
            self.loader_box.configure(values=values)
            self.loader_version_var.set("最新" + (f"（{stable[0]}）" if stable else ""))

        def failed(exc):
            self.loader_version_var.set("获取失败")

        run_async(self, task, on_success=done, on_error=failed)

    # ---------- 安装 ----------

    def _install(self) -> None:
        game = self._selected_game()
        if not game:
            messagebox.showinfo("提示", "请先选择一个游戏版本。", parent=self)
            return
        kind = self.loader_var.get()
        loader_ver = self.loader_version_var.get()
        if loader_ver.startswith("最新") or loader_ver in ("加载中……", "获取失败"):
            loader_ver = ""

        dialog = ProgressDialog(self, f"安装 {game}")

        def task():
            def stage(text):
                dialog.after(0, lambda: dialog.set_message(text))

            def progress(done, total):
                dialog.after(0, lambda: dialog.set_progress(done, total))

            if kind == "vanilla":
                target = game
            elif kind in ("fabric", "quilt"):
                target = install_loader(self.repo, game, loader_ver, kind, stage)
            else:
                from ..install.forge import install_forge
                target = install_forge(self.repo, game, kind, loader_ver, stage, progress)
            self.repo.install(target, stage, progress)
            return target

        def done(target):
            dialog.close()
            self.on_installed(target)
            self.destroy()

        def failed(exc):
            dialog.close()
            messagebox.showerror("安装失败", str(exc), parent=self)

        run_async(self, task, downloader=self.repo.downloader, cancel_event=dialog.cancel_event, on_success=done, on_error=failed)
