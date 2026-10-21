# -*- coding: utf-8 -*-
"""版本管理：搜索、实例卡片列表与常用操作（参照 HMCL 的版本列表）。"""

from ..dpi import px
import tkinter as tk

from ..widgets import EmptyState, FlatButton, GlassFrame, IconTile, ScrollFrame, Tag
from .base import Page


def _kind(version_id: str) -> str:
    text = version_id.lower()
    if "optifine" in text:
        return "OptiFine"
    if "neoforge" in text:
        return "NeoForge"
    if "forge" in text:
        return "Forge"
    if "quilt" in text:
        return "Quilt"
    if "fabric" in text:
        return "Fabric"
    return "原版"


class VersionsPage(Page):
    """版本列表页。"""

    def __init__(self, master, app):
        super().__init__(master, app, bg=app.palette["bg"])
        self.app = app
        self.p = app.palette
        self.query = tk.StringVar(value="")
        self.kind_filter = tk.StringVar(value="全部类型")
        self._build_toolbar()
        self.scroll = ScrollFrame(self, self.p)
        self.scroll.pack(fill="both", expand=True, pady=px((6, 0)))
        self._render()

    def on_show(self) -> None:
        self._render()

    def refresh(self) -> None:
        self._render()

    # ------------------------------------------------------------ 工具栏

    def _build_toolbar(self) -> None:
        p = self.p
        bar = tk.Frame(self, bg=p["bg"])
        bar.pack(fill="x", pady=px((2, 0)))
        search_row = tk.Frame(self, bg=p["bg"])
        search_row.pack(fill="x", pady=px((10, 0)))
        from tkinter import ttk
        kinds = ttk.Combobox(search_row, textvariable=self.kind_filter, state="readonly", width=12,
                             values=("全部类型", "原版", "Fabric", "Forge", "NeoForge", "Quilt", "OptiFine"))
        kinds.pack(side="right", padx=px((10, 0)))
        kinds.bind("<<ComboboxSelected>>", lambda _e: self._render())
        search_box = tk.Frame(search_row, bg=p["surface"], highlightthickness=1,
                              highlightbackground=p["border"])
        search_box.pack(side="left", fill="x", expand=True, padx=px((0, 10)))
        tk.Label(search_box, text="搜索", bg=p["surface"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=px((10, 4)))
        entry = tk.Entry(search_box, textvariable=self.query, relief="flat", bd=0,
                         bg=p["surface"], fg=p["fg"], insertbackground=p["fg"],
                         font=("Microsoft YaHei UI", 10), highlightthickness=0)
        entry.pack(side="left", fill="x", expand=True, ipady=px(7))
        entry.bind("<KeyRelease>", lambda _e: self._render())
        self.count_label = tk.Label(bar, text="", bg=p["bg"], fg=p["muted"],
                                    font=("Microsoft YaHei UI", 9))
        self.count_label.pack(side="left", padx=px((0, 10)))
        FlatButton(bar, p, "导入整合包", command=self.app.import_modpack).pack(side="right")
        FlatButton(bar, p, "新建实例", command=self.app.create_instance).pack(side="right", padx=px(4))
        FlatButton(bar, p, "恢复中心", command=self.app.open_recovery).pack(side="right", padx=px(4))
        FlatButton(bar, p, "安装新版本", kind="accent",
                   command=self.app.install_new_version).pack(side="right", padx=px(8))

    # ------------------------------------------------------------ 列表

    def _filtered(self) -> list[str]:
        query = self.query.get().strip().lower()
        versions = self.app.repo.list_installed()
        kind = self.kind_filter.get()
        if kind != "全部类型":
            versions = [vid for vid in versions if self.app.repo.loader_label(vid) == kind]
        if not query:
            return versions
        result = []
        for vid in versions:
            meta = self.app.instances.get(vid)
            haystack = " ".join((vid, meta.name if meta else "",
                                  meta.group if meta else "")).lower()
            if query in haystack:
                result.append(vid)
        return result

    def _render(self) -> None:
        p = self.p
        self.scroll.reset()
        versions = self._filtered()
        total = len(self.app.repo.list_installed())
        self.count_label.configure(text=f"显示 {len(versions)} 个实例 · 共 {total} 个")
        if not versions:
            self._empty(total == 0)
            return
        content = self.scroll.content
        for vid in versions:
            self._row(content, vid)
        tk.Frame(content, bg=p["bg"], height=px(16)).pack(fill="x")

    def _empty(self, first_run: bool) -> None:
        p = self.p
        EmptyState(self.scroll.content, p,
                   "添加你的第一个游戏实例" if first_run else "没有找到匹配的实例",
                   "安装原版、选择加载器，或导入喜欢的整合包。" if first_run else "试试更短的关键词，或切换为全部类型。",
                   icon="grid", action="安装游戏" if first_run else "清除筛选",
                   command=self.app.install_new_version if first_run else self._clear_filter).pack(fill="x", pady=px(10))

    def _clear_filter(self):
        self.query.set("")
        self.kind_filter.set("全部类型")
        self._render()

    def _row(self, parent, vid: str) -> None:
        p = self.p
        selected = vid == self.app.selected_version
        meta = self.app.instances.get(vid)
        name = self.app.instances.display_name(vid)
        row = GlassFrame(parent, p, cursor="hand2")
        row.pack(fill="x", pady=px(5))
        if selected:
            tk.Frame(row, bg=p["accent"], width=px(3)).pack(side="left", fill="y", pady=px(15))
        row.bind("<Button-1>", lambda _e, v=vid: self.app.set_selected_version(v))

        IconTile(row, p, (name or "?")[:1].upper(), p["accent_soft"],
                 size=46, bg=p["surface"], radius=11).pack(side="left", padx=px(12), pady=px(10))

        buttons = tk.Frame(row, bg=p["surface"])
        buttons.pack(side="right", padx=px(12))
        FlatButton(buttons, p, "启动", kind="accent",
                   command=lambda v=vid: self.app.launch_version(v)).pack(side="left", padx=px(3))
        FlatButton(buttons, p, "设置",
                   command=lambda v=vid: self.app.open_instance_settings(v)).pack(side="left", padx=px(3))
        FlatButton(buttons, p, "删除", kind="ghost",
                   command=lambda v=vid: self.app.delete_version(v)).pack(side="left", padx=px(3))

        info = tk.Frame(row, bg=p["surface"], cursor="hand2")
        info.pack(side="left", fill="x", expand=True, pady=px(10))
        info.bind("<Button-1>", lambda _e, v=vid: self.app.set_selected_version(v))
        title_row = tk.Frame(info, bg=p["surface"])
        title_row.pack(fill="x")
        title = tk.Label(title_row, text=name, bg=p["surface"], fg=p["fg"], justify="left",
                         font=("Microsoft YaHei UI", 11, "bold"), anchor="w", wraplength=px(380))
        title.pack(side="left")
        Tag(title_row, p, self.app.repo.loader_label(vid), p["accent"]).pack(side="left", padx=px(8))
        if meta and meta.group:
            Tag(title_row, p, meta.group, p["surface2"]).pack(side="left")
        isolated = self.app.repo.run_dir(vid) != self.app.repo.game_dir
        detail = f"{vid} · {'独立实例' if isolated else '共享目录'}"
        if meta and meta.last_played:
            detail += f" · 最后游玩 {meta.last_played_text()}"
        if meta and meta.play_seconds:
            detail += f" · 累计 {meta.play_time_text()}"
        tk.Label(info, text=detail, bg=p["surface"], fg=p["muted"], justify="left", wraplength=px(380),
                 font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x")

        def resize_info(event):
            title.configure(wraplength=max(140, event.width - 115))
            for child in info.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(wraplength=max(140, event.width - 10))
        info.bind("<Configure>", resize_info)
        for child in (title, title_row, *title_row.winfo_children(), *info.winfo_children()):
            child.bind("<Button-1>", lambda _e, v=vid: self.app.set_selected_version(v))
