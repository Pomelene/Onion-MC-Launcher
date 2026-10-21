# -*- coding: utf-8 -*-
"""设置页：按 HMCL 的分类组织（游戏 / Java / 外观 / 下载 / 启动器 / 关于）。

交互也向 HMCL 靠拢：左侧分类、右侧表单、修改即保存，不需要再点“保存”。
"""

from ..dpi import px
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from ...java import find_all_java
from ...repository import GameRepository
from ..widgets import FlatButton, ScrollFrame
from .base import Page

SOURCE_NAMES = {"mojang": "Mojang 官方", "bmclapi": "BMCLAPI（推荐）", "mcbbbs": "MCBBS 镜像"}
THEMES = {"system": "跟随系统", "light": "浅色", "dark": "深色",
          "oled": "OLED 墨黑", "retro": "复古终端"}
ACCENTS = {"blue": "宝石蓝", "pink": "樱粉", "green": "苔绿", "purple": "紫罗兰",
           "orange": "落日橙", "teal": "青碧", "amber": "琥珀",
           "system": "跟随系统", "custom": "自定义"}
PRESET_LABELS = {"": "不套用（自定义）", "bridge": "清透科技", "azure": "HMCL 蓝白", "deep-ocean": "深海极简",
                 "forest": "林间晨光",
                 "sakura": "樱花晨光", "cyber": "赛博霓虹", "oled": "OLED 墨黑",
                 "matcha": "抹茶奶绿", "amber": "琥珀夜航", "retro": "复古终端"}
LOG_LEVELS = {"debug": "调试", "info": "信息", "warn": "警告", "error": "错误"}

CATEGORIES = (("game", "游戏"), ("java", "Java"), ("appearance", "外观"),
              ("download", "下载"), ("launcher", "启动器"), ("about", "关于"))


class SettingsPage(Page):
    """分类式设置页。"""

    def __init__(self, master, app):
        super().__init__(master, app, bg=app.palette["bg"])
        self.app = app
        self.p = app.palette
        self._vars: dict[str, tk.Variable] = {}
        body = tk.Frame(self, bg=self.p["bg"])
        body.pack(fill="both", expand=True)
        self._build_side(body)
        self.form = ScrollFrame(body, self.p, bg=self.p["bg"])
        self.form.pack(side="left", fill="both", expand=True, padx=px((14, 0)))
        self.status = tk.Label(self, text="修改即时保存", bg=self.p["bg"],
                               fg=self.p["muted"], font=("Microsoft YaHei UI", 8),
                               anchor="w")
        self.status.pack(fill="x", pady=px((4, 0)))
        self._select("game")

    # ------------------------------------------------------------ 侧栏

    def _build_side(self, parent) -> None:
        p = self.p
        sidebar_bg = p.get("sidebar", p["bg"])
        side = tk.Frame(parent, bg=sidebar_bg, width=px(164))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self._cat_buttons: dict[str, tk.Button] = {}
        for key, label in CATEGORIES:
            button = tk.Button(side, text=f"  {label}", anchor="w", relief="flat", bd=0,
                               highlightthickness=0, cursor="hand2",
                               font=("Microsoft YaHei UI", 10), padx=px(10), pady=px(8),
                               bg=sidebar_bg, fg=p["fg"],
                               activebackground=p["surface2"], activeforeground=p["fg"],
                               command=lambda k=key: self._select(k))
            button.pack(fill="x", padx=px(10), pady=px(1))
            self._cat_buttons[key] = button

    def _select(self, key: str) -> None:
        p = self.p
        sidebar_bg = p.get("sidebar", p["bg"])
        for name, button in self._cat_buttons.items():
            if name == key:
                button.configure(bg=p["accent_soft"],
                                 fg=p.get("accent_text", p["accent"]),
                                 font=("Microsoft YaHei UI", 10, "bold"))
            else:
                button.configure(bg=sidebar_bg, fg=p["fg"],
                                 font=("Microsoft YaHei UI", 10))
        self.form.reset()
        builder = getattr(self, f"_form_{key}", None)
        if builder:
            builder(self.form.content)

    # ------------------------------------------------------------ 通用控件

    def _commit(self, key: str, value) -> None:
        if key == "accent_color" and str(value) == "custom":
            self.status.configure(text="自定义颜色需要填写十六进制并点“应用自定义”")
            return
        try:
            if key in ("theme", "accent_color"):
                self.app.config_obj.set("theme_preset", "")
            self.app.config_obj.set(key, value)
            self.app.config_obj.save()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", f"{key}: {exc}")
            return
        self.status.configure(text=f"已保存 · {time.strftime('%H:%M:%S')}")
        if key == "log_level":
            import logging
            logging.getLogger("craftbridge").setLevel(getattr(logging, str(value).upper(), logging.INFO))
        if key in ("game_dir", "download_source", "max_download_threads", "download_speed_limit", "proxy_host", "proxy_port"):
            self.app.repo = GameRepository(self.app.config_obj)
            self.app.hub.downloader = self.app.repo.downloader
            self.app._sync_version_selector()
        if key in ("theme", "theme_preset", "accent_color", "ui_scale"):
            self.app.after(30, self.app.apply_theme)

    def _commit_int(self, key: str, raw: str, minimum: int = 0,
                    maximum: int = 65535) -> None:
        try:
            value = int(str(raw).strip())
        except ValueError:
            self.status.configure(text="请输入整数")
            return
        self._commit(key, max(minimum, min(maximum, value)))

    def _section(self, parent, title: str, subtitle: str = "") -> tk.Frame:
        p = self.p
        card = tk.Frame(parent, bg=p["surface"], highlightthickness=1,
                        highlightbackground=p["border"])
        card.pack(fill="x", pady=px((0, 10)))
        head = tk.Frame(card, bg=p["surface"])
        head.pack(fill="x", padx=px(18), pady=px((14, 2)))
        tk.Label(head, text=title, bg=p["surface"], fg=p["fg"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(head, text=subtitle, bg=p["surface"], fg=p["muted"],
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=px((2, 0)))
        body = tk.Frame(card, bg=p["surface"])
        body.pack(fill="x", padx=px(18), pady=px((2, 14)))
        return body

    def _row(self, parent, title: str, desc: str = "", control=None) -> tk.Frame:
        p = self.p
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill="x", pady=px(5))
        text = tk.Frame(row, bg=p["surface"])
        if control is not None:
            # Controls are constructed with `parent` as master; explicitly place
            # them inside this row rather than alongside every row in the section.
            control.pack(in_=row, side="right", padx=px((12, 0)))
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, bg=p["surface"], fg=p["fg"],
                 font=("Microsoft YaHei UI", 10), anchor="w").pack(fill="x")
        if desc:
            description = tk.Label(text, text=desc, bg=p["surface"], fg=p["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w", justify="left")
            description.pack(fill="x")
            text.bind("<Configure>", lambda e: description.configure(wraplength=max(px(80), e.width)))
        return row

    def _entry(self, parent, key: str, width: int = 26, commit=None) -> tk.Entry:
        p = self.p
        var = tk.StringVar(value=str(self.app.config_obj.get(key) or ""))
        self._vars[key] = var
        entry = tk.Entry(parent, textvariable=var, width=width, relief="flat", bd=0,
                         bg=p["surface"], fg=p["fg"], insertbackground=p["fg"],
                         highlightthickness=1, highlightbackground=p["border"],
                         highlightcolor=p["accent"], font=("Microsoft YaHei UI", 9))
        handler = commit or (lambda: self._commit(key, var.get().strip()))
        entry.bind("<FocusOut>", lambda _e: handler())
        entry.bind("<Return>", lambda _e: handler())
        return entry

    def _entry_row(self, parent, key: str, title: str, desc: str = "",
                   width: int = 26, commit=None) -> tk.Frame:
        entry = self._entry(parent, key, width, commit)
        return self._row(parent, title, desc, entry)

    def _check_row(self, parent, key: str, title: str, desc: str = "") -> None:
        p = self.p
        var = tk.BooleanVar(value=bool(self.app.config_obj.get(key)))
        self._vars[key] = var
        check = tk.Checkbutton(
            parent, variable=var, bg=p["surface"], activebackground=p["surface"],
            selectcolor=p["surface"], fg=p["accent"], activeforeground=p["accent"],
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            command=lambda: self._commit(key, bool(var.get())))
        self._row(parent, title, desc, check)

    def _option_row(self, parent, key: str, title: str, desc: str,
                    mapping: dict[str, str]) -> None:
        p = self.p
        labels = list(mapping.values())
        current = str(self.app.config_obj.get(key) or "")
        label = mapping.get(current, labels[0])
        var = tk.StringVar(value=label)
        self._vars[key] = var

        def changed(_value=None) -> None:
            chosen = next((k for k, v in mapping.items() if v == var.get()), current)
            self._commit(key, chosen)

        menu = tk.OptionMenu(parent, var, *labels, command=changed)
        menu.configure(bg=p["surface"], fg=p["fg"], activebackground=p["surface2"],
                       activeforeground=p["fg"], relief="flat", bd=0,
                       highlightthickness=0, cursor="hand2",
                       font=("Microsoft YaHei UI", 9), padx=px(6))
        menu["menu"].configure(bg=p["surface"], fg=p["fg"],
                               activebackground=p["accent"], activeforeground=p["accent_fg"])
        self._row(parent, title, desc, menu)

    def _buttons_row(self, parent, title: str, desc: str, buttons) -> None:
        p = self.p
        holder = tk.Frame(parent, bg=p["surface"])
        for text, command, kind in buttons:
            FlatButton(holder, p, text, command=command, kind=kind).pack(side="left", padx=px(3))
        self._row(parent, title, desc, holder)

    def _info_row(self, parent, title: str, value: str) -> None:
        p = self.p
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill="x", pady=px(4))
        tk.Label(row, text=title, bg=p["surface"], fg=p["fg"], width=12, anchor="w",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Label(row, text=value, bg=p["surface"], fg=p["muted"], anchor="w",
                 font=("Consolas", 9)).pack(side="left")

    # ------------------------------------------------------------ 游戏

    def _form_game(self, parent) -> None:
        p = self.p
        body = self._section(parent, "游戏目录", "版本、模组、资源与存档都放在这里")
        holder = tk.Frame(body, bg=p["surface"])
        self._entry(holder, "game_dir", width=34).pack(side="left", ipady=px(3))
        FlatButton(holder, p, "浏览", command=self._browse_game_dir).pack(side="left", padx=px(4))
        FlatButton(holder, p, "打开",
                   command=lambda: self.app.open_folder(self.app.repo.game_dir)).pack(side="left")
        self._row(body, "游戏目录", "留空则使用 F:\\.minecraft", holder)

        body = self._section(parent, "启动行为", "影响每个版本如何使用各自的文件")
        self._check_row(body, "version_isolation", "版本隔离",
                        "开启后每个版本使用独立的 mods / config / 存档目录")
        self._check_row(body, "fullscreen", "全屏启动")
        self._check_row(body, "demo", "试玩模式")
        self._entry_row(body, "server_address", "自动进入服务器",
                        "格式 127.0.0.1:25565，留空则停在主菜单", width=30)

        body = self._section(parent, "窗口与参数", "仅影响下一次启动")
        self._entry_row(body, "window_width", "窗口宽度", "像素", width=10,
                        commit=lambda: self._commit_int(
                            "window_width", self._vars["window_width"].get(), 320, 7680))
        self._entry_row(body, "window_height", "窗口高度", "像素", width=10,
                        commit=lambda: self._commit_int(
                            "window_height", self._vars["window_height"].get(), 240, 4320))
        self._entry_row(body, "game_args", "附加游戏参数", "空格分隔，会追加到参数末尾", width=36)

    def _browse_game_dir(self) -> None:
        path = filedialog.askdirectory(title="选择游戏目录",
                                       initialdir=str(self.app.repo.game_dir))
        if path:
            self._vars["game_dir"].set(path)
            self._commit("game_dir", path)

    # ------------------------------------------------------------ Java

    def _form_java(self, parent) -> None:
        p = self.p
        body = self._section(parent, "Java 路径", "留空时按版本需求自动选择，缺失会自动下载")
        holder = tk.Frame(body, bg=p["surface"])
        self._entry(holder, "java_path", width=32).pack(side="left", ipady=px(3))
        FlatButton(holder, p, "自动检测", command=self._auto_java).pack(side="left", padx=px(4))
        FlatButton(holder, p, "管理 Java", command=self._open_java).pack(side="left")
        self._row(body, "Java 可执行文件", "例如 runtime\\java-runtime-beta\\bin\\java.exe", holder)

        body = self._section(parent, "内存", "按整合包规模调整；太小会 OOM，太大反而增加 GC 压力")
        self._entry_row(body, "min_memory", "最小内存", "MB", width=10,
                        commit=lambda: self._commit_int(
                            "min_memory", self._vars["min_memory"].get(), 512, 65536))
        self._entry_row(body, "max_memory", "最大内存", "MB，建议 4096 以上", width=10,
                        commit=lambda: self._commit_int(
                            "max_memory", self._vars["max_memory"].get(), 512, 65536))

        body = self._section(parent, "JVM 参数", "例如 -XX:+UseG1GC，空格分隔")
        self._entry_row(body, "jvm_args", "附加 JVM 参数", "会插入到 -jar 之前", width=40)

    def _auto_java(self) -> None:
        infos = find_all_java()
        if not infos:
            messagebox.showinfo("Java", "没有在本机发现 Java，可在“管理 Java”里下载官方运行时。")
            return
        best = max(infos, key=lambda item: item.major)
        self._vars["java_path"].set(str(best.path))
        self._commit("java_path", str(best.path))
        messagebox.showinfo("Java", f"已选择 Java {best.major}\n{best.path}")

    def _open_java(self) -> None:
        from ..java_dialog import JavaDialog
        JavaDialog(self.app, self.app)

    # ------------------------------------------------------------ 外观

    def _form_appearance(self, parent) -> None:
        cfg = self.app.config_obj
        body = self._section(parent, "主题", "修改后立即生效，可在任意页面切换")
        self._option_row(body, "theme", "外观模式", "跟随系统会读取 Windows 的亮暗设置", THEMES)
        self._option_row(body, "theme_preset", "预设方案", "保留自定义外观时可选择“不套用”",
                         PRESET_LABELS)

        accent = str(cfg.get("accent_color") or "")
        self._option_row(body, "accent_color", "强调色", "按钮与选中态的主色", ACCENTS)
        if accent.startswith("custom:"):
            self._vars["accent_color"].set(ACCENTS["custom"])

        p = self.p
        custom = tk.Frame(body, bg=p["surface"])
        hex_var = tk.StringVar(
            value=accent[len("custom:"):] if accent.startswith("custom:") else "")
        self._vars["accent_hex"] = hex_var
        entry = tk.Entry(custom, textvariable=hex_var, width=10, relief="flat", bd=0,
                         bg=p["surface"], fg=p["fg"], insertbackground=p["fg"],
                         highlightthickness=1, highlightbackground=p["border"],
                         highlightcolor=p["accent"], font=("Consolas", 9))
        entry.pack(side="left", ipady=px(3))
        FlatButton(custom, p, "应用自定义",
                   command=self._apply_custom_accent).pack(side="left", padx=px(6))
        self._row(body, "自定义颜色", "十六进制，如 #3b82f6", custom)

        body = self._section(parent, "界面", "调整后需要重新布局，窗口会短暂重绘")
        self._entry_row(body, "ui_scale", "界面缩放", "0 表示按系统 DPI 自动", width=10,
                        commit=self._commit_scale)

    def _apply_custom_accent(self) -> None:
        raw = str(self._vars.get("accent_hex").get() or "").strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        if len(raw) not in (4, 7):
            messagebox.showwarning("颜色格式", "请输入 #rgb 或 #rrggbb 形式的颜色。")
            return
        self._vars["accent_color"].set(ACCENTS["custom"])
        self._commit("accent_color", f"custom:{raw}")

    def _commit_scale(self) -> None:
        raw = str(self._vars["ui_scale"].get() or "0").strip()
        try:
            value = float(raw or 0)
        except ValueError:
            self.status.configure(text="缩放需要是数字，0 表示自动")
            return
        self._commit("ui_scale", value)

    # ------------------------------------------------------------ 下载

    def _form_download(self, parent) -> None:
        body = self._section(parent, "下载源", "官方源更稳，镜像在部分网络下更快")
        self._option_row(body, "download_source", "优先下载源", "", SOURCE_NAMES)
        self._entry_row(body, "max_download_threads", "并发线程数", "建议 4–8", width=10,
                        commit=lambda: self._commit_int(
                            "max_download_threads",
                            self._vars["max_download_threads"].get(), 1, 32))
        self._entry_row(body, "download_speed_limit", "限速", "KB/s，0 表示不限", width=10,
                        commit=lambda: self._commit_int(
                            "download_speed_limit",
                            self._vars["download_speed_limit"].get(), 0, 1000000))

        body = self._section(parent, "网络", "代理留空则直连；CurseForge Key 可选")
        self._entry_row(body, "proxy_host", "代理地址", "如 127.0.0.1", width=24)
        self._entry_row(body, "proxy_port", "代理端口", "如 7890", width=10,
                        commit=lambda: self._commit_int(
                            "proxy_port", self._vars["proxy_port"].get(), 0, 65535))
        self._entry_row(body, "curseforge_api_key", "CurseForge API Key",
                        "不填则使用社区只读代理，整合包文件下载可能限流", width=40)

    # ------------------------------------------------------------ 启动器

    def _form_launcher(self, parent) -> None:
        body = self._section(parent, "账号登录", "正版登录使用你注册的 Microsoft 应用；外置登录在账号管理中添加")
        self._entry_row(body, "microsoft_client_id", "Microsoft client_id", "用于设备码登录", width=40)
        body = self._section(parent, "行为", "控制启动器自身的生命周期")
        self._check_row(body, "close_after_launch", "启动游戏后收起启动器", "游戏退出后按下方设置显示或关闭")
        self._check_row(body, "keep_launcher_open", "游戏退出后保持启动器窗口")

        body = self._section(parent, "日志", "调试问题时切到“调试”可看到更多细节")
        self._option_row(body, "log_level", "日志级别", "", LOG_LEVELS)

        body = self._section(parent, "语言", "当前仅提供简体中文")
        self._option_row(body, "language", "界面语言", "", {"zh-CN": "简体中文"})

        body = self._section(parent, "数据目录", "配置、账号与缓存都在这里")
        self._buttons_row(body, "配置目录", str(self.app.config_obj.path.parent), (
            ("打开", lambda: self.app.open_folder(self.app.config_obj.path.parent),
             "neutral"),
        ))

    # ------------------------------------------------------------ 关于

    def _form_about(self, parent) -> None:
        import platform

        body = self._section(parent, "Onion Minecraft Launcher",
                             "Minecraft 启动器 · 参考 HMCL / PCL 的交互")
        self._info_row(body, "版本", self.app.title().split()[-1] if self.app.title() else "0.1.0")
        self._info_row(body, "Python", platform.python_version())
        self._info_row(body, "Tk", str(tk.TkVersion))
        self._info_row(body, "游戏目录", str(self.app.repo.game_dir))
        self._info_row(body, "配置目录", str(self.app.config_obj.path.parent))

        body = self._section(parent, "工具", "常用维护入口")
        self._buttons_row(body, "快捷操作", "", (
            ("打开配置目录", lambda: self.app.open_folder(self.app.config_obj.path.parent),
             "neutral"),
            ("日志与崩溃", lambda: self.app.switch_page("logs"), "neutral"),
            ("恢复默认外观", self._reset_theme, "danger"),
        ))

    def _reset_theme(self) -> None:
        if not messagebox.askyesno("恢复默认外观", "将主题恢复为 HMCL 蓝白，继续？"):
            return
        self._commit("theme", "light")
        self._commit("theme_preset", "azure")
        self._commit("accent_color", "")
