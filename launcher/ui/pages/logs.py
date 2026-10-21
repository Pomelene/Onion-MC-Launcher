# -*- coding: utf-8 -*-
"""日志页：启动器日志 / 游戏日志 / 崩溃报告。"""

from ..dpi import px
import tkinter as tk
from tkinter import ttk

from ..widgets import FlatButton, Tag
from .base import Page


class LogsPage(Page):

    def __init__(self, master, app):
        super().__init__(master, app)
        p = app.palette
        top = tk.Frame(self, bg=p["bg"])
        top.pack(fill="x", pady=px((2, 6)))
        FlatButton(top, p, "刷新", command=self.refresh).pack(side="right")

        body = tk.Frame(self, bg=p["bg"])
        body.pack(fill="both", expand=True, pady=px((4, 10)))
        left = tk.Frame(body, bg=p["bg"])
        left.pack(side="left", fill="y")
        self.source_var = tk.StringVar(value="launcher")
        for key, label in (("launcher", "启动器日志"), ("game", "游戏日志"), ("crash", "崩溃报告")):
            b = tk.Radiobutton(left, text=label, value=key, variable=self.source_var,
                               command=self._load, bg=p["bg"], fg=p["fg"],
                               activebackground=p["bg"], activeforeground=p["fg"],
                               selectcolor=p["bg"], indicatoron=False, relief="flat",
                               font=("Microsoft YaHei UI", 10), padx=px(10), pady=px(5), anchor="w", cursor="hand2")
            b.pack(fill="x")
        text_frame = tk.Frame(body, bg=p["surface"])
        text_frame.pack(side="left", fill="both", expand=True, padx=px((14, 0)))
        self.text = tk.Text(text_frame, bg=p["surface"], fg=p["fg"], state="disabled",
                            wrap="none", font=("Consolas", 9), bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def on_show(self):
        self.refresh()

    def refresh(self):
        self._load()

    def _load(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        source = self.source_var.get()
        lines = self._content_for(source)
        self.text.insert("end", "\n".join(lines) if lines else "（暂无内容）")
        self.text.configure(state="disabled")
        self.text.see("end")

    def _content_for(self, source):
        if source == "launcher":
            return self.app.log_lines
        if source == "game":
            vid = self.app.selected_version
            if not vid:
                return ["请先在“版本”页选择一个版本。"]
            latest = self.app.repo.logs_dir(vid) / "latest.log"
            if not latest.exists():
                return [f"暂无日志：{latest}"]
            try:
                text = latest.read_text(encoding="utf-8", errors="replace")
                return text.splitlines()
            except OSError as e:
                return [f"读取失败：{e}"]
        from launcher.crash import latest_crash_report, summarize
        vid = self.app.selected_version
        run_dir = self.app.repo.run_dir(vid) if vid else self.app.repo.game_dir
        crash = latest_crash_report(run_dir)
        if crash is None:
            return ["没有发现崩溃报告。"]
        from launcher.crash import diagnose_file
        out = [f"崩溃报告：{crash}", "-" * 60]
        out.extend(summarize(crash).splitlines())
        out.append("-" * 60)
        diagnosis = diagnose_file(crash)
        out.append(f"诊断：{diagnosis.get('title')}")
        out.append(f"建议：{diagnosis.get('advice')}")
        if diagnosis.get("evidence"):
            out.append(f"依据：{diagnosis['evidence']}")
        out.append("-" * 60)
        out.append("完整内容：")
        try:
            out.extend(crash.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError as e:
            out.append(f"读取失败：{e}")
        return out
