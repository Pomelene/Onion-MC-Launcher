# -*- coding: utf-8 -*-
"""模组页：模组 / 资源包 / 光影 / 存档四个标签，支持启用禁用、删除、备份恢复、在线搜索。"""

from ..dpi import px
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, filedialog

from ..widgets import Card, EmptyState, FlatButton, ScrollFrame, Tag
from ..util import run_async
from .base import Page

TABS = [("mods", "模组"), ("resourcepacks", "资源包"), ("shaderpacks", "光影"), ("saves", "存档")]


class ModsPage(Page):

    def __init__(self, master, app):
        super().__init__(master, app)
        p = app.palette
        top = tk.Frame(self, bg=p["bg"])
        top.pack(fill="x", pady=px((2, 6)))
        self.vid_label = tk.Label(top, text="", bg=p["bg"], fg=p["fg"],
                                  font=("Microsoft YaHei UI", 11, "bold"))
        self.vid_label.pack(side="left")
        self.tab_var = tk.StringVar(value="mods")
        tabs = tk.Frame(self, bg=p["bg"])
        tabs.pack(fill="x")
        for key, label in TABS:
            b = tk.Radiobutton(tabs, text=label, value=key, variable=self.tab_var,
                               command=self._switch_tab, bg=p["bg"], fg=p["fg"],
                               activebackground=p["bg"], activeforeground=p["fg"],
                               selectcolor=p["bg"], indicatoron=False, relief="flat",
                               font=("Microsoft YaHei UI", 11), padx=px(14), pady=px(6), cursor="hand2")
            b.pack(side="left", padx=px((0, 4)))
        self.search_btn = FlatButton(tabs, p, "搜索安装", command=self._search_install)
        self.search_btn.pack(side="right")
        self.open_btn = FlatButton(tabs, p, "打开目录", command=self._open_dir)
        self.open_btn.pack(side="right", padx=px(6))
        self.scroll = ScrollFrame(self, p)
        self.scroll.pack(fill="both", expand=True, pady=px((10, 10)))

    def on_show(self):
        vid = self.app.selected_version
        self.vid_label.configure(text=f"版本：{vid}" if vid else "未选择版本")
        self.refresh()

    def refresh(self):
        self._switch_tab()

    def _dirs(self):
        vid = self.app.selected_version
        if not vid:
            return None
        repo = self.app.repo
        return {
            "mods": repo.mods_dir(vid),
            "resourcepacks": repo.resourcepacks_dir(vid),
            "shaderpacks": repo.shaderpacks_dir(vid),
            "saves": repo.saves_dir(vid),
        }

    def _switch_tab(self):
        for w in self.scroll.content.winfo_children():
            w.destroy()
        p = self.app.palette
        dirs = self._dirs()
        tab = self.tab_var.get()
        if dirs is None:
            EmptyState(self.scroll.content, p, "先选择一个游戏实例", "模组、资源包和光影将按实例分别管理。",
                       icon="grid", action="选择实例", command=lambda: self.app.switch_page("versions")).pack(fill="x")
            return
        path = dirs[tab]
        if tab == "mods":
            self._mods_list(path)
        elif tab == "saves":
            self._saves_list(path)
        else:
            self._packs_list(path, tab)

    def _mods_list(self, path):
        from launcher.mods import scan_mods
        p = self.app.palette
        infos = scan_mods(path) if path.exists() else []
        if not infos:
            EmptyState(self.scroll.content, p, "为这个世界添加更多可能", "当前实例还没有模组，可以从下载中心寻找喜欢的内容。",
                       icon="package", action="搜索模组", command=self._search_install).pack(fill="x")
            return
        from launcher.mods import duplicate_ids
        dups = {k for k, v in duplicate_ids(infos)}
        for info in infos:
            card = Card(self.scroll.content, p)
            card.pack(fill="x", pady=px(4))
            head = tk.Frame(card.body, bg=p["surface"])
            head.pack(fill="x")
            if not info.enabled:
                Tag(head, p, "已禁用", p["warn"]).pack(side="left")
            if info.mod_id in dups:
                Tag(head, p, "疑似重复", p["danger"]).pack(side="left", padx=px((0, 6)))
            tk.Label(head, text=info.name or info.path.name, bg=p["surface"], fg=p["fg"],
                     font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=px(6))
            tk.Label(head, text=info.version, bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(side="left")
            tk.Label(head, text=info.size_text, bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(side="right")
            btns = tk.Frame(card.body, bg=p["surface"])
            btns.pack(anchor="w", pady=px((8, 0)))
            action = "启用" if not info.enabled else "禁用"
            FlatButton(btns, p, action, command=lambda i=info: self._toggle_mod(i)).pack(side="left", padx=px((0, 6)))
            FlatButton(btns, p, "删除", kind="danger", command=lambda i=info: self._delete_mod(i)).pack(side="left", padx=px(4))
            FlatButton(btns, p, "定位", command=lambda i=info: self.app.open_folder(i.path.parent)).pack(side="left", padx=px(4))

    def _packs_list(self, path, tab):
        from launcher.mods import scan_resourcepacks, scan_shaderpacks
        p = self.app.palette
        fn = scan_resourcepacks if tab == "resourcepacks" else scan_shaderpacks
        packs = fn(path) if path.exists() else []
        if not packs:
            EmptyState(self.scroll.content, p, "还没有添加资源", "添加资源包或光影，让你的世界焕然一新。", action="浏览资源", command=self._search_install).pack(fill="x")
            return
        for pack in packs:
            card = Card(self.scroll.content, p)
            card.pack(fill="x", pady=px(4))
            head = tk.Frame(card.body, bg=p["surface"])
            head.pack(fill="x")
            tk.Label(head, text=pack.name, bg=p["surface"], fg=p["fg"],
                     font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
            tk.Label(head, text=pack.size_text, bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(side="right")
            if pack.description:
                tk.Label(card.body, text=pack.description[:120], bg=p["surface"], fg=p["muted"],
                         font=("Microsoft YaHei UI", 9), wraplength=px(700), justify="left").pack(anchor="w", pady=px((4, 0)))
            FlatButton(card.body, p, "删除", kind="danger",
                       command=lambda x=pack: self._delete_pack(x)).pack(anchor="w", pady=px((8, 0)))

    def _saves_list(self, path):
        from launcher.mods import scan_saves
        p = self.app.palette
        saves = scan_saves(path) if path.exists() else []
        if not saves:
            EmptyState(self.scroll.content, p, "世界等待你来创造", "进入游戏创建世界后，存档会自动显示在这里。", icon="world").pack(fill="x")
            return
        for save in saves:
            card = Card(self.scroll.content, p)
            card.pack(fill="x", pady=px(4))
            head = tk.Frame(card.body, bg=p["surface"])
            head.pack(fill="x")
            tk.Label(head, text=save.name, bg=p["surface"], fg=p["fg"],
                     font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
            from datetime import datetime
            tk.Label(head, text=datetime.fromtimestamp(save.mtime).strftime("%Y-%m-%d %H:%M"),
                     bg=p["surface"], fg=p["muted"], font=("Microsoft YaHei UI", 9)).pack(side="right")
            btns = tk.Frame(card.body, bg=p["surface"])
            btns.pack(anchor="w", pady=px((8, 0)))
            FlatButton(btns, p, "备份", command=lambda s=save: self._backup_save(s)).pack(side="left", padx=px((0, 6)))
            FlatButton(btns, p, "打开", command=lambda s=save: self.app.open_folder(s.path)).pack(side="left", padx=px(4))
            FlatButton(btns, p, "删除", kind="danger",
                       command=lambda s=save: (self._delete_save(s))).pack(side="left", padx=px(4))

    # ---------- 动作 ----------

    def _toggle_mod(self, info):
        from launcher.mods import set_mod_enabled
        try:
            self.app.repo.assert_idle(self.app.selected_version)
            self.app.repo.assert_writable(info.path)
            set_mod_enabled(info, not info.enabled)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("操作失败", str(exc))
        self.refresh()

    def _delete_pack(self, pack):
        from launcher.safety import recycle
        if messagebox.askyesno("移除资源", f"移除 {pack.name}？可在恢复中心找回。"):
            try:
                self.app.repo.assert_idle(self.app.selected_version)
                self.app.repo.assert_writable(pack.path)
                recycle(pack.path, pack.path.parent)
                self.refresh()
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("移除失败", str(exc))

    def _delete_mod(self, info):
        from launcher.mods import delete_mod
        if messagebox.askyesno("确认", f"移除模组 {info.name}？可在恢复中心找回。"):
            try:
                self.app.repo.assert_idle(self.app.selected_version)
                self.app.repo.assert_writable(info.path)
                delete_mod(info)
                self.refresh()
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("移除失败", str(exc))

    def _delete_save(self, save):
        from launcher.saves import delete_save
        if messagebox.askyesno("确认", f"移除存档 {save.name}？可在恢复中心找回。"):
            try:
                self.app.repo.assert_idle(self.app.selected_version)
                self.app.repo.assert_writable(save.path)
                delete_save(save.path)
                self.refresh()
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("移除失败", str(exc))

    def _backup_save(self, save):
        from launcher.saves import backup
        from ..util import ProgressDialog
        vid = self.app.selected_version
        if not vid:
            return
        backups_dir = self.app.repo.run_dir(vid) / "backups"
        try:
            self.app.repo.assert_idle(vid)
            target = backup(save.path, backups_dir)
            messagebox.showinfo("备份完成", f"已备份到：{target}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("备份失败", str(e))

    def _search_install(self):
        if self.tab_var.get() != "mods":
            self.tab_var.set("mods")
            self._switch_tab()
        self.app.switch_page("download")
        self.app.pages["download"].query_var.set("")

    def _open_dir(self):
        dirs = self._dirs()
        if dirs:
            path = dirs[self.tab_var.get()]
            path.mkdir(parents=True, exist_ok=True)
            self.app.open_folder(path)
