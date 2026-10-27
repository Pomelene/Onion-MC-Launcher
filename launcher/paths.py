# -*- coding: utf-8 -*-
"""路径与常量管理。

集中定义启动器的显示名称、版本以及各类默认路径，
避免其它模块各自硬编码字符串。
"""

import sys
from pathlib import Path

#: 启动器显示名称（作为 ${launcher_name} 传给游戏）
LAUNCHER_NAME = "Onion Minecraft Launcher"
#: 启动器版本（作为 ${launcher_version} 传给游戏）
LAUNCHER_VERSION = "0.4.0-T"
# Monotonic release order within each edition; increment for each new release.
LAUNCHER_UPDATE_ORDER = 40
#: 常见 Java 安装根目录（Windows 优先，用于自动发现）
COMMON_JAVA_ROOTS = [
    r"C:\Program Files\Java",
    r"C:\Program Files\Common Files\Oracle\Java\javapath",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\Amazon Corretto",
    r"C:\Program Files (x86)\Java",
    r"C:\Program Files (x86)\Eclipse Adoptium",
]


def app_root() -> Path:
    """启动器所在目录：源码运行时为项目根目录，PyInstaller 打包后为 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_game_dir() -> Path:
    """默认游戏目录：内部直接包含 versions/、assets/、mods/ 等（类似 .minecraft）。"""
    return Path(r"F:\.minecraft")


def default_config_dir() -> Path:
    return app_root() / "config"


def default_settings_path() -> Path:
    return app_root() / "onionmcl.json"


def default_accounts_path() -> Path:
    return app_root() / "onionmcl.json"


def default_log_dir() -> Path:
    """启动器自身日志；与游戏运行目录的 logs 分开。"""
    return app_root() / ".onion" / "logs"


def cache_dir(root=None) -> Path:
    """Launcher caches belong under .onion, apart from Minecraft runtime data."""
    return Path(root or app_root()) / '.onion' / 'cache'
