# -*- coding: utf-8 -*-
"""主页：当前版本 + 启动入口 + 概览 + 最近游玩（对齐 HMCL 的信息层级）。"""

from ..dpi import px
import tkinter as tk
from pathlib import Path

from ..widgets import Card, EmptyState, FlatButton, GlassFrame, IconTile, ScrollFrame, Tag
from .base import Page
from ..theme import mix


def _version_kind(version_id: str) -> str:
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


class HomePage(Page):
    """启动器主页。"""

    def __init__(self, master, app):
        super().__init__(master, app, bg=app.palette["bg"])
        self.app = app
        self.p = app.palette
        self.scroll = ScrollFrame(self, self.p)
        self.scroll.pack(fill="both", expand=True)
        self._build()

    def on_show(self) -> None:
        self._build()

    # ------------------------------------------------------------ 构建

    def _build(self) -> None:
        self.scroll.reset()
        content = self.scroll.content
        self._hero(content)
        self._stats(content)
        self._quick(content)
        self._recent(content)
        self._directory_bar(content)
        tk.Frame(content, bg=self.p["bg"], height=px(18)).pack(fill="x")

    def _current_version(self) -> str:
        versions = self.app.repo.list_installed()
        if self.app.selected_version in versions:
            return self.app.selected_version
        return versions[0] if versions else ""

    def _directory_bar(self, parent) -> None:
        p = self.p
        bar = tk.Frame(parent, bg=p["bg"])
        bar.pack(fill="x", pady=px((12, 0)))
        tk.Label(bar, text="游戏库", bg=p["bg"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=px((14, 8)), pady=px(10))
        tk.Label(bar, text=str(self.app.repo.game_dir), bg=p["bg"], fg=p["muted"],
                 font=("Cascadia Mono", 9)).pack(side="left")
        FlatButton(bar, p, "打开目录", command=lambda: self.app.open_folder(
            self.app.repo.game_dir)).pack(side="right", padx=px(6))

    def _hero(self, parent) -> None:
        p = self.p
        version = self._current_version()
        bg = p["hero"]
        hero = GlassFrame(parent, p, color=bg)
        hero.pack(fill="x", pady=px((2, 14)))
        art = tk.Canvas(hero, width=px(195), height=px(230), bg=bg, highlightthickness=0)
        art.pack(side="right", fill="y", padx=px((0, 16)))
        art.bind("<Configure>", lambda e: self._draw_world(art, e.width, e.height))
        left = tk.Frame(hero, bg=bg)
        left.pack(side="left", fill="both", expand=True, padx=px(26), pady=px(24))
        tk.Label(left, text="MINECRAFT  /  开始新的冒险", bg=bg, fg=p["accent_text"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        name = self.app.instances.display_name(version) if version else "你的世界，从这里开始"
        title = tk.Label(left, text=name, bg=bg, fg=p["fg"], justify="left", anchor="w",
                         font=("Microsoft YaHei UI", 21, "bold"), wraplength=px(430))
        title.pack(fill="x", pady=px((10, 8)))
        left.bind("<Configure>", lambda e: title.configure(wraplength=max(160, e.width)))
        if version:
            tags = tk.Frame(left, bg=bg)
            tags.pack(anchor="w")
            Tag(tags, p, self.app.repo.loader_label(version), p["accent"]).pack(side="left")
            isolated = self.app.repo.run_dir(version) != self.app.repo.game_dir
            tk.Label(tags, text="  独立实例" if isolated else "  共享目录", bg=bg, fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(side="left")
            meta = self.app.instances.get(version)
            tk.Label(left, text=f"上次游玩  {meta.last_played_text()}" if meta and meta.last_played else "已准备就绪，开始第一次冒险",
                     bg=bg, fg=p["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=px((9, 0)))
        else:
            tk.Label(left, text="安装游戏或导入整合包，准备开启一段旅程。", bg=bg,
                     fg=p["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        actions = tk.Frame(left, bg=bg)
        actions.pack(anchor="w", pady=px((18, 0)))
        FlatButton(actions, p, "启动游戏" if version else "安装游戏", kind="accent",
                   font=("Microsoft YaHei UI", 11, "bold"), padx=px(25), pady=px(10),
                   command=(lambda: self.app.launch_version(version)) if version else self.app.install_new_version).pack(side="left")
        if version:
            button = FlatButton(actions, p, "实例设置", command=lambda: self.app.open_instance_settings(version))
            button.set_colors(bg, p["accent_soft"], p["accent_text"])
            button.pack(side="left", padx=px((10, 0)))

    def _draw_world(self, canvas, width, height):
        p = self.p
        canvas.delete("all")
        cx, cy = width / (px(100) / 100) / 2, height / (px(100) / 100) / 2 - 8
        for offset in range(-3, 4):
            canvas.create_line(cx - 110, cy + offset * 22 - 45, cx + 110, cy + offset * 22 + 65,
                               fill=p["art_line"])
            canvas.create_line(cx - 110, cy + offset * 22 + 65, cx + 110, cy + offset * 22 - 45,
                               fill=p["art_line"])
        def cube(x, y, size, height, strength):
            top = mix(p["hero"], p["accent"], strength)
            canvas.create_polygon(x, y, x + size, y + size / 2, x, y + size, x - size, y + size / 2,
                                  fill=top, outline=p["hero"])
            canvas.create_polygon(x - size, y + size / 2, x, y + size, x, y + size + height,
                                  x - size, y + size / 2 + height, fill=mix(top, p["accent"], .24), outline=p["hero"])
            canvas.create_polygon(x, y + size, x + size, y + size / 2, x + size, y + size / 2 + height,
                                  x, y + size + height, fill=mix(top, p["accent"], .47), outline=p["hero"])
        cube(cx, cy - 49, 48, 45, .42)
        cube(cx - 47, cy - 6, 23, 28, .25)
        cube(cx + 48, cy + 16, 23, 24, .63)
        cube(cx + 60, cy - 74, 13, 16, .2)
        canvas.create_oval(cx - 63, cy - 62, cx - 57, cy - 56, fill=p["accent"], outline="")
        canvas.create_text(cx, height / (px(100) / 100) - 22, text="BUILD YOUR NEXT WORLD", fill=p["accent_text"], font=("Segoe UI", 8))
        canvas.scale("all", 0, 0, px(100) / 100, px(100) / 100)

    def _stats(self, parent) -> None:
        p = self.p
        row = tk.Frame(parent, bg=p["bg"])
        row.pack(fill="x", pady=px((0, 12)))
        versions = self.app.repo.list_installed()
        mods_dir = Path(self.app.repo.run_dir(self._current_version())) / "mods" if self._current_version() else self.app.repo.game_dir / "mods"
        mods = len(list(mods_dir.glob("*.jar"))) if mods_dir.is_dir() else 0
        saves = self.app.repo.saves_dir(self._current_version()) if self._current_version() else self.app.repo.game_dir / "saves"
        worlds = len([d for d in saves.iterdir() if d.is_dir() and (d / "level.dat").is_file()]) if saves.is_dir() else 0
        stats = (("已安装版本", len(versions), "versions"), ("当前模组", mods, "mods"), ("当前存档", worlds, "worlds"))
        for index, (label, value, page) in enumerate(stats):
            card = GlassFrame(row, p)
            card.pack(side="left", fill="both", expand=True,
                      padx=(0 if index == 0 else 5, 0 if index == len(stats) - 1 else 5))
            tk.Label(card, text=str(value), bg=p["surface"], fg=p["fg"],
                     font=("Segoe UI", 20, "bold")).pack(side="left", padx=px((18, 8)), pady=px(13))
            FlatButton(card, p, label + "  ›", font=("Microsoft YaHei UI", 9), padx=px(0),
                       command=lambda key=page: self.app.switch_page(key)).pack(side="left")

    def _quick(self, parent) -> None:
        p = self.p
        card = Card(parent, p, "快捷操作")
        card.pack(fill="x", pady=px((0, 12)))
        grid = tk.Frame(card.body, bg=p["surface"])
        grid.pack(fill="x")
        actions = (
            ("安装新版本", self.app.install_new_version),
            ("导入整合包", self.app.import_modpack),
            ("管理 Java", self._open_java),
            ("新建独立实例", self.app.create_instance),
            ("模组与资源", lambda: self.app.switch_page("mods")),
            ("恢复中心", self.app.open_recovery),
        )
        for index, (text, command) in enumerate(actions):
            button = FlatButton(grid, p, text, command=command)
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=px(4), pady=px(4))
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1)

    def _open_java(self) -> None:
        from ..java_dialog import JavaDialog
        JavaDialog(self.app, self.app)

    def _recent(self, parent) -> None:
        p = self.p
        card = Card(parent, p, "最近游玩")
        card.pack(fill="x")
        installed = set(self.app.repo.list_installed())
        items = sorted((m for m in self.app.instances.all() if m.version_id in installed and m.last_played), key=lambda m: m.last_played or 0.0,
                       reverse=True)[:3]
        if not items:
            EmptyState(card.body, p, "下一次冒险，随时开始", "游玩过的实例会自动整理在这里，方便下次继续。",
                       icon="history", action="浏览游戏实例", command=lambda: self.app.switch_page("versions"), compact=True).pack(fill="x")
            return
        for index, meta in enumerate(items):
            if index:
                tk.Frame(card.body, bg=p["border"], height=px(1)).pack(fill="x", pady=px(6))
            row = tk.Frame(card.body, bg=p["surface"])
            row.pack(fill="x")
            title = self.app.instances.display_name(meta.version_id)
            IconTile(row, p, (title or "?")[:1].upper(), p["accent_soft"],
                     size=36, bg=p["surface"], radius=9).pack(side="left", padx=px((0, 10)))
            text = tk.Frame(row, bg=p["surface"])
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=title, bg=p["surface"], fg=p["fg"],
                     font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(text, text=f"{meta.version_id} · {meta.last_played_text()}",
                     bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x")
            FlatButton(row, p, "启动", kind="soft",
                       command=lambda v=meta.version_id: self.app.launch_version(v)).pack(
                side="right")
