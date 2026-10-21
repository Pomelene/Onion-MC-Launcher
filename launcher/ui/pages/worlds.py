# -*- coding: utf-8 -*-
"""存档页：按版本列出世界，支持打开、备份与删除。"""

from ..dpi import px
import os
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog

from ..widgets import Card, EmptyState, FlatButton, ScrollFrame
from .base import Page


class WorldsPage(Page):

    def __init__(self, master, app):
        super().__init__(master, app)
        p = app.palette
        top = tk.Frame(self, bg=p["bg"])
        top.pack(fill="x", pady=px((2, 6)))
        FlatButton(top, p, "刷新", command=self.refresh).pack(side="right")
        FlatButton(top, p, "备份目录", command=self._open_backups).pack(side="right", padx=px((0, 6)))
        FlatButton(top, p, "恢复备份", command=self._restore_backup).pack(side="right", padx=px((0, 6)))

        bar = tk.Frame(self, bg=p["bg"])
        bar.pack(fill="x", pady=px((0, 6)))
        tk.Label(bar, text="版本", bg=p["bg"], fg=p["muted"]).pack(side="left")
        self.version_var = tk.StringVar(value="")
        self.version_menu = tk.OptionMenu(bar, self.version_var, "")
        self.version_menu.configure(bg=p["surface"], fg=p["fg"],
                                    activebackground=p["surface2"],
                                    activeforeground=p["fg"], highlightthickness=0, bd=0)
        self.version_menu.pack(side="left", padx=px(6))
        self.hint = tk.Label(bar, text="", bg=p["bg"], fg=p["muted"],
                             font=("Microsoft YaHei UI", 9))
        self.hint.pack(side="left", padx=px(10))

        self.scroll = ScrollFrame(self, p)
        self.scroll.pack(fill="both", expand=True, pady=px((4, 10)))
        self._versions: list[str] = []

    # ------------------------------------------------------------ 生命周期

    def on_show(self):
        self.refresh()

    def refresh(self):
        self._reload_versions()
        self._reload_worlds()

    def _reload_versions(self):
        p = self.app.palette
        try:
            versions = self.app.repo.list_installed()
        except Exception:  # noqa: BLE001
            versions = []
        versions = sorted(versions)
        if versions != self._versions:
            self._versions = versions
            menu = self.version_menu["menu"]
            menu.delete(0, "end")
            for vid in versions:
                menu.add_command(label=vid, command=lambda v=vid: self._choose(v))
        current = self.app.selected_version or (versions[0] if versions else "")
        if current and current != self.version_var.get():
            self.version_var.set(current)

    def _choose(self, version_id: str):
        self.version_var.set(version_id)
        self.app.set_selected_version(version_id)
        self._reload_worlds()

    def _saves_dir(self):
        vid = self.version_var.get()
        if vid:
            return self.app.repo.saves_dir(vid)
        return self.app.repo.game_dir / "saves"

    def _backups_dir(self):
        return self.app.repo.game_dir / "backups" / "worlds"

    # ------------------------------------------------------------ 列表

    def _reload_worlds(self):
        from launcher.worlds import list_worlds

        p = self.app.palette
        for w in self.scroll.content.winfo_children():
            w.destroy()
        saves = self._saves_dir()
        worlds = list_worlds(saves)
        self.hint.configure(text=f"{saves}（{len(worlds)} 个世界）")
        if not worlds:
            EmptyState(self.scroll.content, p, "世界等待你来创造", "创建世界后，存档会显示在这里。已有备份也可以随时恢复。",
                       icon="world", action="恢复存档备份", command=self._restore_backup).pack(fill="x", pady=px(8))
            return
        for world in worlds:
            self._world_card(world)

    def _world_card(self, world):
        p = self.app.palette
        card = Card(self.scroll.content, p, world.name,
                    f"{world.game_mode or '未知模式'} · {world.version or '未知版本'} · "
                    f"{world.size_text()} · 最后游玩 {world.last_played_text()}")
        card.pack(fill="x", pady=px(4))
        row = tk.Frame(card.body, bg=p["surface"])
        row.pack(fill="x", pady=px((6, 0)))
        FlatButton(row, p, "打开文件夹", command=lambda: self._open_folder(world)).pack(side="left")
        FlatButton(row, p, "备份", command=lambda: self._backup(world)).pack(side="left", padx=px(6))
        FlatButton(row, p, "删除", command=lambda: self._delete(world)).pack(side="left")
        tk.Label(row, text=world.folder, bg=p["surface"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="right")

    # ------------------------------------------------------------ 操作

    def _open_folder(self, world):
        try:
            os.startfile(str(world.dir))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def _open_backups(self):
        target = self._backups_dir()
        target.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def _backup(self, world):
        from launcher.worlds import backup_world

        try:
            self.app.repo.assert_idle(self.version_var.get())
            target = backup_world(world, self._backups_dir())
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("备份失败", str(exc))
            return
        self.app.log(f"已备份存档 {world.name} → {target.name}")
        messagebox.showinfo("备份完成", f"已保存到：\n{target}")

    def _restore_backup(self):
        from pathlib import Path
        from launcher.saves import restore
        from ..util import ProgressDialog, run_async

        version = self.version_var.get()
        if not version:
            messagebox.showinfo("恢复备份", "请先选择要恢复到的实例。", parent=self)
            return
        archive = filedialog.askopenfilename(parent=self, title="选择存档备份",
                                             filetypes=[("存档备份", "*.zip")])
        if not archive:
            return
        target_dir = self._saves_dir()
        try:
            self.app.repo.assert_idle(version)
            self.app.repo.assert_writable(target_dir)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("无法恢复", str(exc), parent=self)
            return
        dialog = ProgressDialog(self, "恢复存档备份", cancelable=False)
        dialog.set_message("正在校验并恢复到新目录，已有世界会保留……")

        def done(target):
            dialog.close()
            self._reload_worlds()
            self.app.log(f"已恢复存档：{target}")
            messagebox.showinfo("恢复完成", f"已恢复到：\n{target}", parent=self)

        run_async(self, lambda: restore(Path(archive), target_dir), on_success=done,
                  on_error=lambda exc: (dialog.close(), messagebox.showerror("恢复失败", str(exc), parent=self)))

    def _delete(self, world):
        from launcher.worlds import delete_world

        if not messagebox.askyesno("删除存档",
                                   f"确定删除世界“{world.name}”吗？\n"
                                   f"目录：{world.dir}\n文件将移入恢复中心，可恢复。"):
            return
        try:
            self.app.repo.assert_idle(self.version_var.get())
            self.app.repo.assert_writable(world.dir)
            delete_world(world)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("移除失败", str(exc))
            return
        self.app.log(f"已删除存档 {world.name}")
        self._reload_worlds()
