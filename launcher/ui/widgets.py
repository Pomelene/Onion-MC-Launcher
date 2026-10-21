# -*- coding: utf-8 -*-
"""通用界面组件：卡片、导航按钮、扁平按钮、滚动容器、图标块。

视觉方向对齐 HMCL：浅灰导航 + 白色内容区、主色按钮、行式表单。
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from .dpi import px
from .icons import photo, button_icon

FONT = "Microsoft YaHei UI"


def round_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int,
               radius: int, **kwargs) -> None:
    """在 Canvas 上画圆角矩形（Tk 没有原生圆角）。"""
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1,
        x2, y1 + radius, x2, y2 - radius, x2, y2,
        x2 - radius, y2, x1 + radius, y2, x1, y2,
        x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=12, **kwargs)


class FlatButton(tk.Canvas):
    """圆角按钮：原生分辨率绘制，支持键盘、焦点和禁用状态。"""

    def __init__(self, master, palette, text, command=None, kind="neutral", font=None, icon=None, **kw):
        from tkinter import font as tkfont
        self.palette, self.command = palette, command
        self._text, self._state = text, kw.pop("state", "normal")
        self._icon_name = icon or button_icon(text)
        self._explicit_icon = icon
        self._pressed = False
        self._kind = kind
        self._font = tkfont.Font(master, font=font or (FONT, 10))
        self._padx, self._pady = kw.pop("padx", px(14)), kw.pop("pady", px(7))
        self._bg, self._hover = {
            "neutral": (master.cget("bg"), palette["hover"]),
            "soft": (palette["accent_soft"], palette["hover"]),
            "accent": (palette["accent"], palette["accent_hover"]),
            "ghost": (master.cget("bg"), palette["hover"]),
            "danger": (palette["danger"], palette["danger"]),
        }.get(kind, (palette["surface"], palette["hover"]))
        self._fg = palette["accent_fg"] if kind in ("accent", "danger") else palette["accent_text"] if kind == "soft" else palette["fg"]
        self._inside = self._focused = False
        super().__init__(master, bg=master.cget("bg"), highlightthickness=0, bd=0,
                         width=self._font.measure(text) + self._padx * 2 + (px(24) if self._icon_name else 0),
                         height=max(px(36), self._font.metrics("linespace") + self._pady * 2),
                         takefocus=True, cursor="hand2", **kw)
        self.bind("<Configure>", lambda e: self._paint())
        self.bind("<Enter>", lambda e: self._hovering(True))
        self.bind("<Leave>", lambda e: self._hovering(False))
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<FocusIn>", lambda e: self._focus(True))
        self.bind("<FocusOut>", lambda e: self._focus(False))

    def _hovering(self, inside):
        self._inside = inside
        self._paint()

    def _focus(self, focused):
        self._focused = focused
        self._paint()

    def _press(self, event):
        if self._state != "disabled":
            self.focus_set()
            self._pressed = True
            self._paint()

    def _release(self, event):
        pressed = self._pressed
        self._pressed = False
        self._paint()
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _paint(self):
        from PIL import Image, ImageDraw, ImageTk
        from .theme import mix
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 3 or h < 3:
            return
        disabled = self._state == "disabled"
        fill = self._hover if self._inside and not disabled else self._bg
        if self._pressed and not disabled:
            fill = mix(fill, self.palette["fg"], .12)
        if disabled:
            fill = mix(self._bg, self.master.cget("bg"), .65)
        # 超采样边缘；不再使用 Canvas 的锯齿多边形模拟圆角。
        scale = 3
        shape = Image.new("RGBA", (w*scale, h*scale))
        draw = ImageDraw.Draw(shape)
        draw.rounded_rectangle((scale, scale, (w-1)*scale, (h-1)*scale), radius=px(5)*scale,
                               fill=fill, outline=self.palette["accent"] if self._focused else None,
                               width=scale)
        self._shape = ImageTk.PhotoImage(shape.resize((w,h), Image.Resampling.LANCZOS), master=self)
        self.create_image(0, 0, image=self._shape, anchor="nw")
        fg = self.palette["muted"] if disabled else self._fg
        gap = px(8) if self._icon_name else 0
        icon_width = px(16) if self._icon_name else 0
        content_width = self._font.measure(self._text) + gap + icon_width
        x = (w-content_width)/2
        if self._icon_name:
            self._icon_photo = photo(self, self._icon_name, fg, icon_width)
            self.create_image(x, h/2, image=self._icon_photo, anchor="w")
        self.create_text(x+icon_width+gap, h/2, text=self._text, font=self._font, fill=fg, anchor="w")

    def invoke(self):
        if self._state != "disabled" and self.command:
            return self.command()

    def configure(self, cnf=None, **kw):
        if not hasattr(self, "_font"):
            return super().configure(cnf, **kw)
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        for key, attr in (("text", "_text"), ("state", "_state"), ("command", "command"),
                          ("bg", "_bg"), ("activebackground", "_hover"), ("fg", "_fg")):
            if key in kw:
                setattr(self, attr, kw.pop(key))
        self._icon_name = self._explicit_icon or button_icon(self._text)
        if kw:
            super().configure(**kw)
        super().configure(width=self._font.measure(self._text) + self._padx*2 + (px(24) if self._icon_name else 0))
        self._paint()

    config = configure

    def set_colors(self, bg, hover, fg):
        self._bg, self._hover, self._fg = bg, hover, fg
        self._paint()


class NavButton(tk.Canvas):
    """侧栏导航：柔和圆角选中态和独立线性图标。"""

    def __init__(self, master, palette, text, icon="·", command=None):
        self.palette, self._text, self.command = palette, text, command
        self._active = self._inside = self._focused = False
        self._icon = {"⌂": "\ue80f", "▦": "\ue8f1", "↓": "\ue896", "◈": "\ue7fc",
                      "▤": "\ue8b7", "≡": "\ue9d9", "⚙": "\ue713"}.get(icon, icon)
        super().__init__(master, height=px(44), bg=palette["sidebar"], bd=0,
                         highlightthickness=0, cursor="hand2", takefocus=True)
        self.bind("<Configure>", lambda e: self._paint())
        self.bind("<Enter>", lambda e: self._hovering(True))
        self.bind("<Leave>", lambda e: self._hovering(False))
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Return>", lambda e: self.command())
        self.bind("<space>", lambda e: self.command())
        self.bind("<FocusIn>", lambda e: self._focus(True))
        self.bind("<FocusOut>", lambda e: self._focus(False))

    def _focus(self, focused):
        self._focused = focused
        self._paint()

    def _hovering(self, inside):
        self._inside = inside
        self._paint()

    def _paint(self):
        p = self.palette
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if self._active or self._inside or self._focused:
            round_rect(self, 0, 0, w, h, px(11), fill=p["accent_soft"] if self._active else p["hover"], outline="")
        fg = p["accent_text"] if self._active else p["muted"]
        if self._active:
            round_rect(self, px(1), h/2-px(8), px(4), h/2+px(8), px(2), fill=p["accent"], outline="")
        name = {"\ue80f": "play", "\ue8f1": "grid", "\ue896": "download", "\ue7fc": "package", "\ue8b7": "world", "\ue9d9": "history", "\ue713": "settings"}.get(self._icon, "grid")
        self._nav_icon = photo(self, name, fg, px(18))
        self.create_image(px(24), h/2, image=self._nav_icon)
        self.create_text(px(46), h/2, text=self._text, anchor="w", fill=p["fg"] if not self._active else fg,
                         font=(FONT, 10, "bold" if self._active else "normal"))

    def set_active(self, active):
        self._active = active
        self._paint()


class IconTile(tk.Canvas):
    """圆角小图标块（版本列表/主页用），中间放一个字。"""

    def __init__(self, master, palette: dict, text: str, color: Optional[str] = None,
                 size: int = 44, bg: Optional[str] = None, radius: int = 10):
        base = bg or palette["surface"]
        super().__init__(master, width=px(size), height=px(size), bg=base,
                         highlightthickness=0, bd=0)
        color = color or palette["accent_soft"]
        round_rect(self, 0, 0, px(size), px(size), px(radius), fill=color)
        self.create_text(px(size // 2), px(size // 2), text=text,
                         fill=palette.get("accent_text", palette["accent"]) if color != palette["accent"] else palette["accent_fg"],
                         font=(FONT, max(9, size // 3), "bold"))


class GlassFrame(tk.Frame):
    """以圆角色层形成面板，子控件仍使用原生 Tk 布局与焦点。"""

    def __init__(self, master, palette, color=None, **kw):
        self.panel_color = color or palette["surface"]
        super().__init__(master, bg=self.panel_color, **kw)
        outer = master.cget("bg")
        self._glass = tk.Canvas(self, bg=outer, bd=0, highlightthickness=0)
        self._glass.place(x=0, y=0, relwidth=1, relheight=1)
        self._glass.tk.call("lower", self._glass._w)
        self._glass.bind("<Configure>", self._paint_glass)

    def _paint_glass(self, event):
        self._glass.delete("all")
        round_rect(self._glass, 0, 0, event.width, event.height, px(14),
                   fill=self.panel_color, outline="")


class Card(GlassFrame):
    """白色卡片容器（可带标题与说明）。"""

    def __init__(self, master, palette: dict, title: str = "", subtitle: str = "", **kw):
        kw.setdefault("bd", 0)
        super().__init__(master, palette, **kw)
        self.palette = palette
        if title or subtitle:
            head = tk.Frame(self, bg=palette["surface"])
            head.pack(fill="x", padx=px(18), pady=px((14, 8)))
            if title:
                tk.Label(head, text=title, bg=palette["surface"], fg=palette["fg"],
                         font=(FONT, 11, "bold")).pack(anchor="w")
            if subtitle:
                tk.Label(head, text=subtitle, bg=palette["surface"], fg=palette["muted"],
                         font=(FONT, 9)).pack(anchor="w", pady=px((2, 0)))
        self.body = tk.Frame(self, bg=palette["surface"])
        self.body.pack(fill="both", expand=True, padx=px(18), pady=px((0, 16)))


class EmptyState(GlassFrame):
    """统一空状态：图标、标题、说明和可选的下一步操作。"""
    def __init__(self, master, palette, title, description, icon="package", action=None, command=None, compact=False):
        super().__init__(master, palette)
        content = tk.Frame(self, bg=palette["surface"])
        content.pack(fill="x", padx=px(24), pady=px(20 if compact else 38))
        self._empty_icon = photo(self, icon, palette["accent_text"], px(28 if compact else 36))
        tk.Label(content, image=self._empty_icon, bg=palette["surface"]).pack(pady=px((0, 12)))
        tk.Label(content, text=title, bg=palette["surface"], fg=palette["fg"],
                 font=(FONT, 11, "bold")).pack()
        text = tk.Label(content, text=description, bg=palette["surface"], fg=palette["muted"],
                        font=(FONT, 9), justify="center", wraplength=px(440))
        text.pack(pady=px((6, 0)))
        content.bind("<Configure>", lambda e: text.configure(wraplength=max(px(100), e.width-px(12))))
        if action and command:
            FlatButton(content, palette, action, command=command, kind="soft").pack(pady=px((16, 0)))


class Tag(tk.Label):
    """小型色块标签（版本类型、状态等）。"""

    def __init__(self, master, palette: dict, text: str, color: Optional[str] = None):
        color = color or palette["muted"]
        try:
            from .theme import relative_luminance
            fg = "#ffffff" if relative_luminance(color) < 0.45 else "#1f2328"
        except Exception:  # noqa: BLE001
            fg = "#ffffff"
        from .theme import mix, readable_fg
        background = mix(palette["surface"], color, 0.12)
        foreground = mix(color, readable_fg(palette["surface"]), 0.3)
        super().__init__(master, text=text, bg=background, fg=foreground,
                         font=(FONT, 8), padx=px(7), pady=px(2))


class ScrollFrame(tk.Frame):
    """带滚动条的可滚动容器；内容放到 .content 里。"""

    def __init__(self, master, palette: dict, bg: Optional[str] = None):
        super().__init__(master, bg=bg or palette["bg"])
        self.canvas = tk.Canvas(self, bg=bg or palette["bg"], highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.canvas, bg=bg or palette["bg"])
        self._win = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_content(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def reset(self) -> None:
        """清空内容，便于重绘。"""
        for child in self.content.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


def labeled_entry(parent, palette: dict, label: str, var: tk.StringVar, row: int,
                 width: int = 30) -> ttk.Entry:
    tk.Label(parent, text=label, bg=parent["bg"], fg=palette["fg"],
             font=(FONT, 10)).grid(row=row, column=0, sticky="w", pady=px(4))
    entry = ttk.Entry(parent, textvariable=var, width=width)
    entry.grid(row=row, column=1, sticky="ew", pady=px(4), padx=px((10, 0)))
    return entry
