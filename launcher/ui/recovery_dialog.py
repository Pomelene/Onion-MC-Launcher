"""Restore recoverable instance, mod, pack and world removals."""
from .dpi import px, geometry
import json
import tkinter as tk
from tkinter import ttk, messagebox

from ..safety import contained, restore_recycled
from .util import center


class RecoveryDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("恢复中心")
        self.geometry(geometry("780x420"))
        self.transient(app)
        self.grab_set()
        ttk.Label(self, text="移除的文件会保留在原目录的 .craftbridge-trash 中；恢复不会覆盖同名文件。",
                  padding=14).pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=("name", "location"), show="headings")
        self.tree.heading("name", text="名称")
        self.tree.heading("location", text="原位置")
        self.tree.column("name", width=230)
        self.tree.column("location", width=490)
        self.tree.pack(fill="both", expand=True, padx=px(14))
        ttk.Button(self, text="恢复所选", command=self._restore).pack(anchor="e", padx=px(14), pady=px(14))
        self._reload()
        center(self, app)

    def _reload(self):
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        repo = self.app.repo
        parents = {repo.versions_dir, *(repo.game_dir / d for d in ("mods", "saves", "resourcepacks", "shaderpacks"))}
        for vid in repo.list_installed():
            parents.update(repo.run_dir(vid) / d for d in ("mods", "saves", "resourcepacks", "shaderpacks"))
        for parent in sorted(parents):
            trash = parent / ".craftbridge-trash"
            if not trash.is_dir():
                continue
            for record in sorted(trash.glob("*.recovery.json"), reverse=True):
                try:
                    contained(record, repo.game_dir)
                    data = json.loads(record.read_text(encoding="utf-8"))
                    from pathlib import Path
                    target = Path(data["stored"])
                    contained(target, trash)
                    if not target.exists():
                        continue
                    key = str(record)
                    self.entries[key] = (target, parent)
                    self.tree.insert("", "end", iid=key, values=(Path(data["original"]).name, data["original"]))
                except (OSError, ValueError, KeyError):
                    continue

    def _restore(self):
        selected = self.tree.selection()
        if not selected:
            return
        target, parent = self.entries[selected[0]]
        try:
            restored = restore_recycled(target, parent)
        except (OSError, ValueError) as exc:
            messagebox.showerror("恢复失败", str(exc), parent=self)
            return
        self.app._sync_version_selector()
        self.app.set_status(f"已恢复：{restored.name}")
        self._reload()
