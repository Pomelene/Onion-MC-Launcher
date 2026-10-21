# -*- coding: utf-8 -*-
"""实例设置对话框：展示信息（名称/分组/备注）与启动配置（Java/内存/窗口）。"""

from .dpi import px
import tkinter as tk
from tkinter import filedialog, messagebox

from ..java import find_all_java
from ..version_settings import SCHEMA
from .util import center
from .widgets import FlatButton


class InstanceDialog(tk.Toplevel):
    """一个实例的名称、分组、备注与启动覆盖项。"""

    def __init__(self, master, app, version_id: str):
        super().__init__(master)
        self.app = app
        self.version_id = version_id
        self.p = app.palette
        self.title(f"实例设置 · {version_id}")
        self.configure(bg=self.p["bg"])
        self.transient(master)
        self.resizable(False, False)

        body = tk.Frame(self, bg=self.p["bg"])
        body.pack(fill="both", expand=True, padx=px(18), pady=px(14))
        self.vars: dict[str, tk.Variable] = {}
        meta = app.instances.get(version_id)
        overrides = app.version_settings.get(version_id)

        def add(label: str, key: str, value: str, width: int = 30) -> tk.Entry:
            row = tk.Frame(body, bg=self.p["bg"])
            row.pack(fill="x", pady=px(3))
            tk.Label(row, text=label, width=12, anchor="w", bg=self.p["bg"],
                     fg=self.p["fg"], font=("Microsoft YaHei UI", 10)).pack(side="left")
            var = tk.StringVar(value=value)
            entry = tk.Entry(row, textvariable=var, width=width, bg=self.p["surface"],
                             fg=self.p["fg"], insertbackground=self.p["fg"], relief="flat",
                             bd=0, highlightthickness=1, highlightbackground=self.p["border"],
                             highlightcolor=self.p["border"])
            entry.pack(side="left", ipady=px(2))
            self.vars[key] = var
            return row

        add("名称", "name", meta.name)
        add("分组", "group", meta.group)

        notes_row = tk.Frame(body, bg=self.p["bg"])
        notes_row.pack(fill="x", pady=px(3))
        tk.Label(notes_row, text="备注", width=12, anchor="nw", bg=self.p["bg"],
                 fg=self.p["fg"], font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.notes = tk.Text(notes_row, width=40, height=3, bg=self.p["surface"],
                             fg=self.p["fg"], insertbackground=self.p["fg"], relief="flat",
                             bd=0, highlightthickness=1, highlightbackground=self.p["border"])
        self.notes.pack(side="left")
        self.notes.insert("1.0", meta.notes)

        tk.Frame(body, bg=self.p["border"], height=px(1)).pack(fill="x", pady=px(8))

        java_row = self._row(body, "Java 路径")
        self.vars["java_path"] = tk.StringVar(value=str(overrides.get("java_path") or ""))
        tk.Entry(java_row, textvariable=self.vars["java_path"], width=34,
                 bg=self.p["surface"], fg=self.p["fg"], insertbackground=self.p["fg"],
                 relief="flat", bd=0, highlightthickness=1,
                 highlightbackground=self.p["border"]).pack(side="left", ipady=px(2))
        FlatButton(java_row, self.p, "浏览", command=self._browse_java).pack(side="left", padx=px(4))
        FlatButton(java_row, self.p, "自动", command=self._auto_java).pack(side="left")

        add("最小内存 (MB)", "min_memory", str(overrides.get("min_memory") or ""), 12)
        add("最大内存 (MB)", "max_memory", str(overrides.get("max_memory") or ""), 12)
        add("窗口宽度", "width", str(overrides.get("width") or ""), 12)
        add("窗口高度", "height", str(overrides.get("height") or ""), 12)
        add("服务器地址", "server_address", str(overrides.get("server_address") or ""), 30)
        add("JVM 参数", "jvm_args", str(overrides.get("jvm_args") or ""), 40)
        add("游戏参数", "game_args", str(overrides.get("game_args") or ""), 40)
        for key, label in (("fullscreen", "全屏"), ("isolate", "独立游戏目录")):
            row = self._row(body, label)
            choices = {"跟随全局": "", "开启": "true", "关闭": "false"}
            value = overrides.get(key)
            var = tk.StringVar(value="跟随全局" if value is None else ("开启" if value else "关闭"))
            self.vars[key] = var
            tk.OptionMenu(row, var, *choices).pack(side="left")

        buttons = tk.Frame(body, bg=self.p["bg"])
        buttons.pack(fill="x", pady=px((12, 0)))
        FlatButton(buttons, self.p, "保存", command=self._save, kind="accent").pack(side="right")
        FlatButton(buttons, self.p, "取消", command=self.destroy).pack(side="right", padx=px(6))
        tk.Label(buttons, text=f"版本 ID：{version_id}  改动仅影响该实例",
                 bg=self.p["bg"], fg=self.p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left")

        self.grab_set()
        center(self)

    def _row(self, parent, label: str) -> tk.Frame:
        row = tk.Frame(parent, bg=self.p["bg"])
        row.pack(fill="x", pady=px(3))
        tk.Label(row, text=label, width=12, anchor="w", bg=self.p["bg"],
                 fg=self.p["fg"], font=("Microsoft YaHei UI", 10)).pack(side="left")
        return row

    def _browse_java(self):
        path = filedialog.askopenfilename(title="选择 java 可执行文件",
                                          filetypes=[("java", "java.exe"), ("所有文件", "*.*")])
        if path:
            self.vars["java_path"].set(path)

    def _auto_java(self):
        infos = find_all_java()
        if not infos:
            messagebox.showinfo("提示", "未发现可用的 Java。", parent=self)
            return
        best = next((i for i in infos if i.major in (21, 17)), infos[0])
        self.vars["java_path"].set(str(best.path))

    def _save(self):
        try:
            self.app.instances.update(
                self.version_id,
                name=self.vars["name"].get(),
                group=self.vars["group"].get(),
                notes=self.notes.get("1.0", "end").strip(),
            )
            overrides = {}
            for key, typ in SCHEMA.items():
                raw = self.vars.get(key)
                if raw is None:
                    continue
                text = str(raw.get()).strip()
                if not text:
                    continue
                try:
                    if typ is bool:
                        if text == "跟随全局":
                            continue
                        overrides[key] = text == "开启"
                    else:
                        overrides[key] = typ(text)
                except (TypeError, ValueError):
                    continue
            self.app.version_settings.set(self.version_id, overrides)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.app.log(f"已更新实例设置：{self.version_id}")
        self.destroy()
        self.app.pages["versions"].refresh()
