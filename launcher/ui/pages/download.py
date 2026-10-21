# -*- coding: utf-8 -*-
"""下载页：Modrinth 下载中心 + 安装原版/加载器入口。"""

from ..dpi import px
import tkinter as tk
from tkinter import messagebox, ttk

from ..widgets import Card, EmptyState, FlatButton, ScrollFrame
from ..util import run_async
from .base import Page

KINDS = ["mod", "resourcepack", "shader", "modpack"]
LOADERS = ["fabric", "forge", "neoforge", "quilt", ""]


class DownloadPage(Page):

    def __init__(self, master, app):
        super().__init__(master, app)
        p = app.palette
        top = tk.Frame(self, bg=p["bg"])
        top.pack(fill="x", pady=px((2, 6)))
        FlatButton(top, p, "安装原版 / 加载器", command=app.install_new_version, kind="accent").pack(side="right")
        FlatButton(top, p, "安装 OptiFine", command=self._open_optifine).pack(side="right", padx=px(8))

        bar = tk.Frame(self, bg=p["bg"])
        bar.pack(fill="x", pady=px(4))
        self.kind_var = tk.StringVar(value="mod")
        self.kind_label = tk.StringVar(value="模组")
        kind_names = {"模组": "mod", "资源包": "resourcepack", "光影": "shader", "整合包": "modpack"}
        k = ttk.Combobox(bar, textvariable=self.kind_label, values=tuple(kind_names), state="readonly", width=9)
        k.bind("<<ComboboxSelected>>", lambda e: (self.kind_var.set(kind_names[self.kind_label.get()]), self._kind_changed()))
        k.pack(side="left")
        self.query_var = tk.StringVar()
        q = tk.Entry(bar, textvariable=self.query_var, bg=p["surface"], fg=p["fg"],
                     insertbackground=p["fg"], relief="flat", bd=0, highlightthickness=1,
                     highlightbackground=p["border"], highlightcolor=p["border"], width=34)
        q.pack(side="left", padx=px(8))
        q.bind("<Return>", lambda e: self._search())
        FlatButton(bar, p, "搜索", command=self._search, kind="accent").pack(side="left")
        tk.Label(bar, text="加载器", bg=p["bg"], fg=p["muted"]).pack(side="left", padx=px((16, 4)))
        self.loader_var = tk.StringVar(value="")
        self.loader_label = tk.StringVar(value="不限加载器")
        self.loader_names = {"不限加载器": "", "Fabric": "fabric", "Forge": "forge", "NeoForge": "neoforge", "Quilt": "quilt"}
        lc = ttk.Combobox(bar, textvariable=self.loader_label, values=tuple(self.loader_names), state="readonly", width=12)
        lc.bind("<<ComboboxSelected>>", lambda e: self.loader_var.set(self.loader_names[self.loader_label.get()]))
        lc.pack(side="left")
        tk.Label(bar, text="游戏版本", bg=p["bg"], fg=p["muted"]).pack(side="left", padx=px((12, 4)))
        self.game_var = tk.StringVar(value="")
        g = tk.Entry(bar, textvariable=self.game_var, width=10, bg=p["surface"], fg=p["fg"],
                     insertbackground=p["fg"], relief="flat", bd=0, highlightthickness=1,
                     highlightbackground=p["border"], highlightcolor=p["border"])
        g.pack(side="left")

        status_bar = tk.Frame(self, bg=p["bg"])
        status_bar.pack(fill="x", pady=px((2, 4)))
        self._syncing = False
        self.source_summary = tk.Label(status_bar, text="镜像源：等待同步", bg=p["bg"],
                                       fg=p["muted"], font=("Microsoft YaHei UI", 8))
        self.source_summary.pack(side="left")
        FlatButton(status_bar, p, "同步", command=self._sync_sources).pack(side="right")

        self.scroll = ScrollFrame(self, p)
        self.scroll.pack(fill="both", expand=True, pady=px((8, 10)))
        EmptyState(self.scroll.content, p, "发现你的下一份灵感", "搜索模组、资源包、光影或整合包。选择实例后，会自动匹配游戏版本与加载器。", icon="search").pack(fill="x")

    def on_show(self):
        vid = self.app.selected_version
        if vid:
            from launcher.modpack import _base_version, _detect_loader
            self.game_var.set(_base_version(self.app.repo, vid))
            self.loader_var.set(_detect_loader(self.app.repo, vid)[0])
        self.loader_label.set(next((label for label, value in self.loader_names.items() if value == self.loader_var.get()), "不限加载器"))
        self._sync_sources()

    def _kind_changed(self):
        if self.kind_var.get() in ("resourcepack", "shader"):
            self.loader_var.set("")
            self.loader_label.set("不限加载器")

    def _sync_sources(self):
        """后台并行同步 8 个信息源，状态实时刷新到状态条。"""
        if self._syncing:
            return
        self._syncing = True
        self.app.hub.refresh_async(on_status=self._on_source_status)
        self.after(400, self._poll_sync)

    def _on_source_status(self, status):
        try:
            self.after(0, self._apply_status, status.key, status.label(), status.state)
        except Exception:  # noqa: BLE001
            pass

    def _apply_status(self, key=None, text="", state="ok"):
        """把 8 个信息源的状态收敛成一行摘要，避免状态栏拥挤。"""
        statuses = self.app.hub.status_list()
        total = len(statuses)
        ok = sum(1 for item in statuses if item.state == "ok")
        failed = sum(1 for item in statuses if item.state == "fail")
        loading = sum(1 for item in statuses if item.state == "loading")
        if loading:
            summary = f"镜像源：同步中 {total - loading}/{total}"
        elif failed:
            summary = f"镜像源：{ok}/{total} 就绪，{failed} 个失败"
        else:
            summary = f"镜像源：{ok}/{total} 就绪"
        p = self.app.palette
        color = p["accent"] if loading else (p["danger"] if failed and not ok else p["muted"])
        try:
            self.source_summary.configure(text=summary, fg=color)
        except tk.TclError:
            pass

    def _poll_sync(self):
        states = [s.state for s in self.app.hub.status_list()]
        if any(state == "loading" for state in states):
            self.after(400, self._poll_sync)
            return
        self._syncing = False
        self.app.set_status(f"多源同步完成：游戏版本 {len(self.app.hub.game_versions())} 个")

    def refresh(self):
        pass

    def _open_optifine(self):
        from ..optifine_dialog import OptiFineDialog
        OptiFineDialog(self.app, self.app)

    def _search(self):
        kind = self.kind_var.get()
        query = self.query_var.get().strip()
        if not query:
            self.app.set_status("请输入搜索关键词")
            return
        self._clear()
        tk.Label(self.scroll.content, text="搜索中……", bg=self.app.palette["bg"],
                 fg=self.app.palette["muted"]).pack(anchor="w", pady=px(10))
        from launcher.catalog import search
        game = self.game_var.get().strip()
        loader = self.loader_var.get().strip().lower()
        run_async(self, lambda: search(self.app.repo.downloader, kind, query, game, loader, limit=30),
                  on_success=self._render_results,
                  on_error=lambda e: (messagebox.showerror("搜索失败", str(e)), self._clear()))

    def _clear(self):
        for w in self.scroll.content.winfo_children():
            w.destroy()

    def _render_results(self, data):
        self._clear()
        p = self.app.palette
        hits = data.get("hits") or []
        if not hits:
            EmptyState(self.scroll.content, p, "没有找到匹配的内容", "试试其他关键词，或放宽游戏版本与加载器条件。", icon="search").pack(fill="x")
            return
        for hit in hits[:20]:
            self._hit_card(hit)

    def _hit_card(self, hit):
        p = self.app.palette
        card = Card(self.scroll.content, p)
        card.pack(fill="x", pady=px(4))
        head = tk.Frame(card.body, bg=p["surface"])
        head.pack(fill="x")
        tk.Label(head, text=hit.get("title") or "?", bg=p["surface"], fg=p["fg"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        author = hit.get("author") or ""
        if author:
            tk.Label(head, text=f"by {author}", bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(side="left", padx=px(8))
        tk.Label(head, text=f"下载 {hit.get('downloads') or 0}", bg=p["surface"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="right")
        desc = (hit.get("description") or "")[:160]
        if desc:
            tk.Label(card.body, text=desc, bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9), wraplength=px(760), justify="left").pack(anchor="w", pady=px((4, 0)))
        btns = tk.Frame(card.body, bg=p["surface"])
        btns.pack(anchor="w", pady=px((8, 0)))
        pid = hit.get("project_id") or ""
        FlatButton(btns, p, "安装", kind="accent",
                   command=lambda pid=pid: self._install_project(pid)).pack(side="left", padx=px((0, 6)))
        FlatButton(btns, p, "打开网页",
                   command=lambda u=pid: self.app.open_url(f"https://modrinth.com/project/{u}")).pack(side="left")

    def _install_project(self, project_id):
        vid = self.app.selected_version or (self.app.repo.list_installed() or [None])[0]
        if not vid:
            messagebox.showinfo("提示", "请先在“版本”页安装一个游戏版本。")
            return
        kind = self.kind_var.get()
        loader = self.loader_var.get().strip().lower()
        game = self.game_var.get().strip()
        from launcher.catalog import versions
        self.app.set_status(f"正在查询 {project_id} 的可用版本……")
        run_async(self, lambda: (versions(self.app.repo.downloader, project_id), project_id, kind, game, loader),
                  on_success=lambda r: self._pick_and_download(*r),
                  on_error=lambda e: messagebox.showerror("查询失败", str(e)))

    def _pick_and_download(self, vlist, project_id, kind, game, loader):
        from launcher.catalog import pick_version
        chosen = pick_version(vlist, game, loader) if (game or loader) else (vlist[0] if vlist else None)
        if not chosen:
            messagebox.showinfo("提示", "没有适配当前版本/加载器的文件。")
            return
        vid = self.app.selected_version or (self.app.repo.list_installed() or [None])[0]
        if not vid:
            return
        run_dir = self.app.repo.run_dir(vid)
        target_dir = {
            "mod": run_dir / "mods",
            "resourcepack": run_dir / "resourcepacks",
            "shader": run_dir / "shaderpacks",
            "modpack": run_dir / "modpacks",
        }.get(kind) or (run_dir / "mods")
        try:
            self.app.repo.assert_idle(vid)
            self.app.repo.assert_writable(target_dir)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("无法安装", str(exc))
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        from launcher.catalog import download_version
        from launcher.mods import install_dependencies
        def work() -> tuple:
            path = download_version(self.app.repo.downloader, chosen, target_dir)
            if kind == "modpack":
                from launcher.modpack import import_modpack
                imported = import_modpack(self.app.repo, path)
                return path, imported
            deps = (install_dependencies(self.app.repo.downloader, chosen.get("id"), target_dir, game, loader)
                    if kind == "mod" else [])
            return path, len(deps)
        run_async(self, work,
                  on_success=lambda r: self._installed_ok(*r),
                  on_error=lambda e: messagebox.showerror("下载失败", str(e)))

    def _installed_ok(self, path, deps):
        if isinstance(deps, str):
            self.app.set_selected_version(deps)
            self.app.switch_page("versions")
            messagebox.showinfo("整合包安装完成", f"已创建独立实例：{deps}")
            return
        self.app.set_status(f"已下载：{path.name}（自动补 {deps} 个依赖）")
        messagebox.showinfo("完成", f"已安装到：{path}\n自动安装依赖 {deps} 个。")
