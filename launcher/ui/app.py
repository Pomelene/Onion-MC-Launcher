# -*- coding: utf-8 -*-
"""主窗口：左侧导航 + 多页内容（仿 PCL/HMCL 的现代启动器布局）。"""

from .dpi import px
import os
import sys
import shlex
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..accounts import AccountStore, offline_uuid
from ..config import Config
from ..crash import latest_crash_report, summarize
from ..instance import InstanceStore
from ..launch import Account, LaunchSettings, launch
from ..paths import (LAUNCHER_NAME, LAUNCHER_VERSION, app_root, default_accounts_path,
                     default_settings_path)
from ..repository import GameRepository
from ..sources import ALL_SOURCES
from ..version_settings import VersionSettingsStore
from .accounts_dialog import AccountsDialog
from .install_dialog import InstallDialog
from .instance_dialog import InstanceDialog
from .pages import (DownloadPage, HomePage, LogsPage, ModsPage, SettingsPage,
                    VersionsPage, WorldsPage)
from .theme import apply_dpi, apply_style, resolve_theme
from .util import ProgressDialog, center, run_async
from .icons import photo
from .widgets import GlassFrame, FlatButton, NavButton, round_rect


class App(tk.Tk):
    """启动器主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.config_obj = Config(default_settings_path())
        from ..log import setup_logging
        setup_logging(app_root() / "logs", self.config_obj.get("log_level"), to_console=False)
        self.accounts = AccountStore(default_accounts_path())
        self.repo = GameRepository(self.config_obj)
        self.instances = InstanceStore(default_settings_path())
        self.version_settings = VersionSettingsStore(
            default_settings_path())
        self._game_started_at = 0.0
        self._process = None
        self._launch_pending = False
        self._selected_version = self.config_obj.get("selected_version") or ""
        self.log_lines: list[str] = []
        self.palette: dict = {}
        self._theme_name = ""
        from launcher.aggregator import InfoHub
        self.hub = InfoHub(self.repo.downloader)
        self.hub.load_cache()

        try:
            resources = Path(getattr(sys, "_MEIPASS", app_root()))
            self.iconbitmap(str(resources / "assets" / "craftbridge.ico"))
        except tk.TclError:
            pass
        self.title(f"{LAUNCHER_NAME} {LAUNCHER_VERSION}")
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(px(1240), max(px(960), screen_w - px(80)))
        height = min(px(780), max(px(620), screen_h - px(80)))
        self.geometry(f"{width}x{height}")
        self.minsize(min(px(1060), width), min(px(660), height))
        self._version_labels: dict[str, str] = {}
        self.apply_theme()
        self._build_ui()
        self.refresh_account_label()
        self.switch_page("home")
        center(self)

    # ------------------------------------------------------------ 主题

    def apply_theme(self) -> None:
        mode = self.config_obj.get("theme") or "system"
        preset = self.config_obj.get("theme_preset") or ""
        accent = self.config_obj.get("accent_color") or ""
        self._theme_name = resolve_theme(mode)
        apply_dpi(self, float(self.config_obj.get("ui_scale") or 0))
        self.palette = apply_style(self, mode, accent, preset)
        if getattr(self, "_shell", None) is not None:
            current = getattr(self, "current_page_name", "home")
            self._shell.destroy()
            self._build_ui()
            self.refresh_account_label()
            self.switch_page(current)

    PAGE_META = {
        "home": ("主页", "选择版本并启动游戏"),
        "versions": ("版本管理", "已安装的游戏版本与加载器"),
        "download": ("下载中心", "安装原版、加载器、模组与整合包"),
        "mods": ("模组与资源", "管理当前实例的模组、资源包与光影"),
        "worlds": ("存档", "世界列表、备份与删除"),
        "logs": ("日志与崩溃", "启动日志与崩溃诊断"),
        "settings": ("设置", "游戏、Java、外观与下载"),
    }

    def _rebuild_pages(self) -> None:
        for w in self._page_container.winfo_children():
            w.destroy()
        self.pages = {}
        for key, cls in (("home", HomePage), ("versions", VersionsPage),
                         ("download", DownloadPage), ("mods", ModsPage),
                         ("worlds", WorldsPage), ("logs", LogsPage),
                         ("settings", SettingsPage)):
            page = cls(self._page_container, self)
            page.pack(fill="both", expand=True)
            page.place_forget()
            self.pages[key] = page

    # ------------------------------------------------------------ 界面搭建

    def _build_ui(self) -> None:
        p = self.palette
        self.status_var = tk.StringVar(value="就绪")
        self._shell = tk.Frame(self, bg=p["bg"])
        self._shell.pack(fill="both", expand=True)

        sidebar_bg = p.get("sidebar", p["bg"])
        sidebar = tk.Frame(self._shell, bg=sidebar_bg, width=px(208))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(self._shell, bg=p["border"], width=px(1)).pack(side="left", fill="y")

        # 品牌区
        brand = tk.Frame(sidebar, bg=sidebar_bg)
        brand.pack(fill="x", padx=px(18), pady=px((20, 18)))
        icon = tk.Canvas(brand, width=px(34), height=px(34), bg=sidebar_bg, highlightthickness=0)
        icon.pack(side="left")
        round_rect(icon, 1, 1, 33, 33, 9, fill=p["accent"])
        icon.create_text(17, 17, text="C", fill=p["accent_fg"],
                         font=("Microsoft YaHei UI", 15, "bold"))
        icon.scale("all", 0, 0, px(100) / 100, px(100) / 100)
        brand_text = tk.Frame(brand, bg=sidebar_bg)
        brand_text.pack(side="left", padx=px((10, 0)))
        tk.Label(brand_text, text=LAUNCHER_NAME, bg=sidebar_bg, fg=p["fg"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        tk.Label(brand_text, text=f"v{LAUNCHER_VERSION} · Minecraft", bg=sidebar_bg,
                 fg=p["muted"], font=("Microsoft YaHei UI", 8)).pack(anchor="w")

        def group(text: str) -> None:
            tk.Label(sidebar, text=text, bg=sidebar_bg, fg=p["muted"],
                     font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(
                fill="x", padx=px(24), pady=px((10, 2)))

        self._nav_buttons = {}
        group("游戏")
        for key, text, glyph in (
                ("home", "主页", "⌂"),
                ("versions", "版本管理", "▦"),
                ("download", "下载中心", "↓"),
                ("mods", "模组与资源", "◈"),
        ):
            b = NavButton(sidebar, p, text, glyph, command=lambda k=key: self.switch_page(k))
            b.pack(fill="x", padx=px(12), pady=px(1))
            self._nav_buttons[key] = b
        group("内容")
        for key, text, glyph in (("worlds", "存档", "▤"),):
            b = NavButton(sidebar, p, text, glyph, command=lambda k=key: self.switch_page(k))
            b.pack(fill="x", padx=px(12), pady=px(1))
            self._nav_buttons[key] = b
        group("启动器")
        for key, text, glyph in (("logs", "日志与崩溃", "≡"), ("settings", "设置", "⚙")):
            b = NavButton(sidebar, p, text, glyph, command=lambda k=key: self.switch_page(k))
            b.pack(fill="x", padx=px(12), pady=px(1))
            self._nav_buttons[key] = b

        # 底部账号卡片
        account = GlassFrame(sidebar, p, cursor="hand2")
        account.pack(side="bottom", fill="x", padx=px(12), pady=px((8, 12)))
        account.bind("<Button-1>", lambda _e: self.open_accounts())
        avatar = tk.Canvas(account, width=px(32), height=px(32), bg=p["surface"],
                           highlightthickness=0, cursor="hand2")
        avatar.pack(side="left", padx=px((10, 8)), pady=px(9))
        avatar.create_oval(1, 1, 31, 31, fill=p["accent_soft"], outline="")
        self._avatar_canvas = avatar
        self._avatar_text = avatar.create_text(16, 16, text="", fill=p["accent"],
                                              font=("Microsoft YaHei UI", 10, "bold"))
        avatar.scale("all", 0, 0, px(100) / 100, px(100) / 100)
        self._avatar_icon = photo(avatar, "account", p["accent_text"], px(20))
        self._avatar_image = avatar.create_image(px(16), px(16), image=self._avatar_icon)
        avatar.bind("<Button-1>", lambda e: self.open_accounts())
        account_text = tk.Frame(account, bg=p["surface"], cursor="hand2")
        account_text.pack(side="left", fill="x", expand=True)
        account_text.bind("<Button-1>", lambda _e: self.open_accounts())
        self.account_name = tk.Label(account_text, text="添加游戏账号", bg=p["surface"],
                                     fg=p["fg"], font=("Microsoft YaHei UI", 9, "bold"),
                                     anchor="w")
        self.account_name.pack(fill="x", pady=px((9, 0)))
        self.account_type = tk.Label(account_text, text="正版 · 离线 · 外置", bg=p["surface"],
                                     fg=p["muted"], font=("Microsoft YaHei UI", 8),
                                     anchor="w")
        self.account_type.pack(fill="x", pady=px((0, 9)))
        for label in (self.account_name, self.account_type):
            label.bind("<Button-1>", lambda e: self.open_accounts())

        tk.Frame(sidebar, bg=sidebar_bg, height=px(1)).pack(side="bottom", fill="x", padx=px(12))
        FlatButton(sidebar, p, "打开游戏目录", kind="ghost",
                   command=lambda: self.open_folder(self.repo.game_dir)).pack(
            side="bottom", fill="x", padx=px(12), pady=px(4))

        # 右侧：顶栏 + 页面 + 状态栏
        right = tk.Frame(self._shell, bg=p["bg"])
        right.pack(side="left", fill="both", expand=True)
        header = tk.Frame(right, bg=p["bg"], height=px(66))
        header.pack(fill="x", padx=px(26), pady=px((20, 0)))
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg=p["bg"])
        title_box.pack(side="left", fill="y")
        self.page_title = tk.Label(title_box, text="主页", bg=p["bg"], fg=p["fg"],
                                   font=("Microsoft YaHei UI", 19, "bold"), anchor="w")
        self.page_title.pack(anchor="w", pady=px((2, 0)))
        self.page_sub = tk.Label(title_box, text="", bg=p["bg"], fg=p["muted"],
                                 font=("Microsoft YaHei UI", 9), anchor="w")
        self.page_sub.pack(anchor="w", pady=px((2, 0)))

        actions = tk.Frame(header, bg=p["bg"])
        actions.pack(side="right", fill="y")
        tk.Label(actions, text="当前实例", bg=p["bg"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=px((0, 6)))
        self.version_var = tk.StringVar(value="")
        self.version_combo = ttk.Combobox(actions, textvariable=self.version_var,
                                          state="readonly", width=23,
                                          font=("Microsoft YaHei UI", 9))
        self.version_combo.pack(side="left", ipady=px(2))
        self.version_combo.bind("<<ComboboxSelected>>", self._on_version_choice)
        self.header_launch = FlatButton(actions, p, "启动游戏", command=self._launch_selected,
                                        kind="accent", padx=px(20), pady=px(8))
        self.header_launch.pack(side="left", padx=px(8))

        tk.Frame(right, bg=p["border"], height=px(1)).pack(fill="x", padx=px(26), pady=px((10, 0)))
        self._page_container = tk.Frame(right, bg=p["bg"])
        self._page_container.pack(fill="both", expand=True, padx=px(26), pady=px((14, 0)))
        tk.Label(right, textvariable=self.status_var, bg=p["bg"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", padx=px(26), pady=px((4, 8)))

        self.pages = {}
        self.current_page_name = "home"
        self._rebuild_pages()
        self._sync_version_selector()

    # ------------------------------------------------------------ 导航

    def switch_page(self, name: str) -> None:
        if name not in self.pages:
            return
        self.current_page_name = name
        for key, page in self.pages.items():
            if key == name:
                page.pack(fill="both", expand=True)
                page.lift()
                page.on_show()
            else:
                page.pack_forget()
        for key, b in self._nav_buttons.items():
            b.set_active(key == name)
        title, subtitle = self.PAGE_META.get(name, (name, ""))
        self.page_title.configure(text=title)
        self.page_sub.configure(text=subtitle)
        self._sync_version_selector()

    # ------------------------------------------------------------ 顶栏版本选择

    def _sync_version_selector(self) -> None:
        combo = getattr(self, "version_combo", None)
        if combo is None:
            return
        versions = self.repo.list_installed()
        if versions and self._selected_version not in versions:
            self._selected_version = versions[0]
        labels: list[str] = []
        self._version_labels = {}
        for vid in versions:
            label = self.instances.display_name(vid)
            if label in self._version_labels:
                label = f"{label}（{vid}）"
            self._version_labels[label] = vid
            labels.append(label)
        combo.configure(values=labels)
        if not versions:
            self.version_var.set("尚未安装游戏")
            combo.configure(state="disabled")
            self.header_launch.configure(text="安装游戏", command=self.install_new_version)
            return
        combo.configure(state="readonly")
        self.header_launch.configure(text="启动游戏", command=self._launch_selected)
        if self._selected_version in versions:
            for label, vid in self._version_labels.items():
                if vid == self._selected_version:
                    self.version_var.set(label)
                    break
        elif not self.version_var.get() or self.version_var.get() not in self._version_labels:
            self.version_var.set(labels[0])

    def _on_version_choice(self, _event=None) -> None:
        vid = self._version_labels.get(self.version_var.get())
        if vid:
            self.set_selected_version(vid)

    def _launch_selected(self) -> None:
        if not self.repo.list_installed():
            messagebox.showinfo("还没有版本", "请先在“下载中心”安装一个游戏版本。")
            self.switch_page("download")
            return
        self.launch_version(self.selected_version or self._version_labels.get(
            self.version_var.get(), ""))

    # ------------------------------------------------------------ 状态 / 日志

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def log(self, text: str) -> None:
        from ..log import get_logger
        get_logger().info(text)
        self.log_lines.append(text)
        if len(self.log_lines) > 2000:
            self.log_lines = self.log_lines[-2000:]
        self.set_status(text[:80])

    def refresh_account_label(self) -> None:
        acc = self.accounts.current()
        name_widget = getattr(self, "account_name", None)
        if name_widget is None:
            return
        if acc is None:
            name_widget.configure(text="添加游戏账号")
            self.account_type.configure(text="正版 · 离线 · 外置")
            self._avatar_text_set("")
            return
        kind = {"microsoft": "正版账号", "authlib": "外置账号"}.get(acc.type, "离线账号")
        name_widget.configure(text=acc.username)
        self.account_type.configure(text=kind)
        self._avatar_text_set((acc.username or "?")[:1].upper())

    def _avatar_text_set(self, text: str) -> None:
        canvas = getattr(self, "_avatar_canvas", None)
        if canvas is None:
            return
        try:
            canvas.itemconfigure(self._avatar_text, text=text)
            canvas.itemconfigure(self._avatar_image, state="hidden" if text else "normal")
        except Exception:  # noqa: BLE001
            pass

    def open_accounts(self) -> None:
        dialog = AccountsDialog(self, self.accounts, self.config_obj)
        self.wait_window(dialog)
        self.refresh_account_label()
        if "home" in self.pages:
            self.pages["home"].on_show()

    # ------------------------------------------------------------ 版本信息

    @property
    def selected_version(self) -> str:
        return self._selected_version

    def set_selected_version(self, vid: str) -> None:
        self._selected_version = vid
        self.config_obj.set("selected_version", vid)
        self._sync_version_selector()
        if "versions" in self.pages:
            self.pages["versions"].refresh()
        if "home" in self.pages:
            self.pages["home"].on_show()

    def version_kind(self, vid: str) -> str:
        try:
            return self.repo.version_summary(vid)["type"]
        except Exception:  # noqa: BLE001
            return "unknown"

    def version_info(self, vid: str) -> str:
        try:
            info = self.repo.version_summary(vid)
        except Exception as exc:  # noqa: BLE001
            return f"读取失败：{exc}"
        parts = [f"{info['type']}"]
        if info.get("release_time"):
            parts.append(info["release_time"][:10])
        try:
            rv = self.repo.resolver.resolve(vid)
            if rv.java_major:
                parts.append(f"Java {rv.java_major}")
            return " · ".join(parts)
        except Exception:  # noqa: BLE001
            return " · ".join(parts)

    def source_name(self) -> str:
        key = self.config_obj.get("download_source") or "mojang"
        return ALL_SOURCES.get(key, key)

    def open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def open_url(self, url: str) -> None:
        try:
            os.startfile(url)
        except OSError:
            import webbrowser
            webbrowser.open(url)

    # ------------------------------------------------------------ 安装

    def install_new_version(self) -> None:
        InstallDialog(self, self.repo, on_installed=self._after_install)

    def _after_install(self, version_id: str) -> None:
        self.set_selected_version(version_id)
        self.switch_page("versions")
        self.log(f"已安装版本：{version_id}")

    def import_modpack(self) -> None:
        from ..modpack import import_modpack
        path = filedialog.askopenfilename(
            parent=self, title="选择整合包",
            filetypes=[("整合包", "*.mrpack *.zip"), ("所有文件", "*.*")])
        if not path:
            return
        dialog = ProgressDialog(self, "导入整合包")

        def task() -> str:
            def stage(text):
                dialog.after(0, lambda: dialog.set_message(text))

            def progress(done, total):
                dialog.after(0, lambda: dialog.set_progress(done, total))

            return import_modpack(self.repo, Path(path), stage, progress)

        def done(version_id):
            dialog.close()
            self.set_selected_version(version_id)
            self.switch_page("versions")
            self.log(f"整合包已导入：{version_id}")

        def failed(exc):
            dialog.close()
            messagebox.showerror("导入失败", str(exc))

        run_async(self, task, downloader=self.repo.downloader, cancel_event=dialog.cancel_event, on_success=done, on_error=failed)

    # ------------------------------------------------------------ 账号

    def require_account(self) -> Account | None:
        record = self.accounts.current()
        if record is None:
            messagebox.showinfo("提示", "请先在“账号管理”中添加一个离线或正版账号。")
            self.open_accounts()
            return None
        return Account(username=record.username, uuid=record.uuid,
                       access_token=record.access_token or "0",
                       user_type=record.user_type, authlib_url=record.authlib_url if hasattr(record, "authlib_url") else "")

    # ------------------------------------------------------------ 启动

    def launch_version(self, vid: str) -> None:
        if not vid:
            self.set_status("请先选择一个版本")
            return
        if self._launch_pending or (self._process is not None and self._process.proc.poll() is None):
            messagebox.showwarning("提示", "游戏已经在运行中。")
            return
        account = self.require_account()
        if account is None:
            return

        self._launch_pending = True
        dialog = ProgressDialog(self, "准备启动")

        def task() -> tuple:
            def stage(text):
                dialog.after(0, lambda: dialog.set_message(text))

            def progress(done, total):
                dialog.after(0, lambda: dialog.set_progress(done, total))

            rv = self.repo.install(vid, stage, progress)
            if dialog.cancelled:
                raise RuntimeError("已取消")
            from ..java import resolve_java
            vs = self.version_settings.resolve(vid, self.config_obj)
            java = resolve_java(rv.java_major, vs.get("java_path") or self.config_obj.get("java_path") or "",
                                self.repo.downloader, stage, progress)
            if java is None:
                raise RuntimeError("未找到可用的 Java，请在设置中指定 java 路径")
            record = self.accounts.ensure_fresh(self.accounts.get(account.uuid))
            if record is None:
                raise RuntimeError("账号续期失败，请重新登录")
            fresh = Account(username=record.username, uuid=record.uuid,
                            access_token=record.access_token or "0", user_type=record.user_type,
                            authlib_url=record.authlib_url, client_id=record.client_id, xuid=record.xuid)
            injector = self._authlib_jar(fresh.authlib_url)
            return rv, java, vs, fresh, injector

        run_async(self, task, downloader=self.repo.downloader, cancel_event=dialog.cancel_event,
                  on_success=lambda r: self._start_game(dialog, r, account),
                  on_error=lambda e: (setattr(self, "_launch_pending", False), dialog.close(),
                                      messagebox.showerror("启动失败", str(e))))

    def _start_game(self, dialog: ProgressDialog, result, account: Account) -> None:
        dialog.close()
        self._launch_pending = False
        rv, java, vs, account, injector = result
        settings = LaunchSettings(
            java_path=str(java.path),
            min_memory=int(vs.get("min_memory") or self.config_obj.get("min_memory") or 2048),
            max_memory=int(vs.get("max_memory") or self.config_obj.get("max_memory") or 4096),
            width=int(vs.get("width") or self.config_obj.get("window_width") or 854),
            height=int(vs.get("height") or self.config_obj.get("window_height") or 480),
            fullscreen=bool(vs["fullscreen"]),
            demo=bool(self.config_obj.get("demo")),
            server_address=vs["server_address"],
            launcher_name=LAUNCHER_NAME,
            launcher_version=LAUNCHER_VERSION,
            extra_jvm_args=shlex.split(vs["jvm_args"]),
            extra_game_args=shlex.split(vs["game_args"]),
            authlib_injector_jar=injector,
        )
        self.set_status(f"正在运行：{rv.id}")
        self.log(f"正在启动 {self.instances.display_name(rv.id)}（Java {java.major}）")
        run_dir = self.repo.run_dir(rv.id)
        try:
            self._process = launch(
                self.repo, rv, account, settings, str(java.path),
                on_log=lambda line, is_err: self.after(0, lambda: self._game_log(line, is_err)),
                on_exit=lambda code: self.after(0, lambda: self._on_game_exit(code, run_dir, rv.id)),
            )
            self.instances.record_launch(rv.id)
            self._game_started_at = time.time()
            if self.config_obj.get("close_after_launch"):
                self.withdraw()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("启动失败", str(exc))

    def _authlib_jar(self, url: str) -> str:
        if not url:
            return ""
        jar = self.repo.game_dir / ".cache" / "authlib-injector.jar"
        try:
            from ..auth.authlib import ensure_injector
            ensure_injector(self.repo.downloader, jar)
            return str(jar)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"外置登录组件下载失败：{exc}") from exc

    def _game_log(self, line: str, is_err: bool) -> None:
        self.log(("[错误] " if is_err else "") + line)

    def _on_game_exit(self, code: int, run_dir: Path, version_id: str = "") -> None:
        self._process = None
        self.set_status("就绪")
        started_at = self._game_started_at
        if version_id and self._game_started_at:
            elapsed = max(0.0, time.time() - self._game_started_at)
            self.instances.add_play_time(version_id, elapsed)
            self._game_started_at = 0.0
        self.log(f"游戏已退出（代码 {code}）")
        crash = latest_crash_report(run_dir, started_at)
        if crash is not None:
            try:
                text = summarize(crash)
                self.log(f"检测到崩溃报告：{crash.name}")
                self.log(text)
            except Exception:  # noqa: BLE001
                pass
        if self.config_obj.get("keep_launcher_open"):
            self.deiconify()
        else:
            self.after(500, self.destroy)

    def stop_game(self) -> None:
        if self._process is None or self._process.proc.poll() is not None:
            self.set_status("当前没有正在运行的游戏")
            return
        self._process.stop()
        self.log("已请求结束游戏。")

    # ------------------------------------------------------------ 其它操作

    def verify_version(self, vid: str) -> None:
        dialog = ProgressDialog(self, "校验文件", cancelable=False)

        def task() -> list:
            return self.repo.verify(vid)

        def done(problems):
            dialog.close()
            if problems:
                messagebox.showwarning("校验结果", "发现以下问题：\n\n" + "\n".join(problems[:20]))
            else:
                messagebox.showinfo("校验结果", "文件完整。")

        run_async(self, task, on_success=done,
                  on_error=lambda e: (dialog.close(), messagebox.showerror("校验失败", str(e))))

    def delete_version(self, vid: str) -> None:
        if not messagebox.askyesno("确认删除", f"移除版本 {vid}？\n文件将移入 versions/.craftbridge-trash，可在恢复中心找回。"):
            return
        try:
            stored = self.repo.delete_version(vid)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("移除失败", str(exc))
            return
        if self._selected_version == vid:
            self._selected_version = ""
        self.switch_page("versions")
        self.log(f"已移除版本：{vid} → {stored}")

    def create_instance(self) -> None:
        base = self.selected_version
        if not base:
            messagebox.showinfo("新建实例", "请先安装并选择一个基础版本。", parent=self)
            return
        name = simpledialog.askstring("新建独立实例", f"基础版本：{base}\n实例名称：", parent=self)
        if not name:
            return
        try:
            vid = self.repo.create_instance(base, name.strip())
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("创建失败", str(exc), parent=self)
            return
        self.set_selected_version(vid)
        self.switch_page("versions")
        self.set_status(f"已创建独立实例：{vid}")

    def open_recovery(self) -> None:
        from .recovery_dialog import RecoveryDialog
        RecoveryDialog(self)

    def open_instance_settings(self, vid: str) -> None:
        if not vid:
            self.set_status("请先选择一个版本")
            return
        InstanceDialog(self, self, vid)

    def export_version(self, vid: str) -> None:
        from ..modpack import export_mrpack
        default = f"{vid}.mrpack"
        out = filedialog.asksaveasfilename(parent=self, title="导出整合包",
                                           defaultextension=".mrpack", initialfile=default)
        if not out:
            return
        dialog = ProgressDialog(self, "导出整合包", cancelable=False)

        def task() -> Path:
            return export_mrpack(self.repo, vid, Path(out))

        def done(path):
            dialog.close()
            self.log(f"已导出：{path}")
            messagebox.showinfo("完成", f"已导出到：{path}")

        run_async(self, task, on_success=done,
                  on_error=lambda e: (dialog.close(), messagebox.showerror("导出失败", str(e))))


def main() -> None:
    app = App()
    app.mainloop()
