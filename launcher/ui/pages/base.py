# -*- coding: utf-8 -*-
"""页面基类。"""

import tkinter as tk


class Page(tk.Frame):
    """每个页面是一个 Frame；切换时调用 on_show() 刷新数据。"""

    def __init__(self, master, app, **kw):
        kw.setdefault("bg", app.palette["bg"])
        super().__init__(master, **kw)
        self.app = app

    def on_show(self) -> None:
        pass

    def refresh(self) -> None:
        pass
