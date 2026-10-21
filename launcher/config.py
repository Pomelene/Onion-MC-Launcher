# -*- coding: utf-8 -*-
"""全局配置（settings.json）读写。

配置以 JSON 保存、结构平坦，未知字段自动忽略；
所有字段均有默认值，线程安全。
"""

import json
import threading
from pathlib import Path
from typing import Any

from .paths import default_game_dir,LAUNCHER_NAME

#: 需要按类型强制的键（避免 settings.json 手工编辑引入错类型）
_INT_KEYS = {"min_memory", "max_memory", "window_width", "window_height",
             "proxy_port", "max_download_threads", "download_speed_limit",
             "sandbox_budget_mb"}
_BOOL_KEYS = {"fullscreen", "demo", "version_isolation",
              "close_after_launch", "keep_launcher_open",
              "allow_newer_java", "foreign_mode"}
_FLOAT_KEYS = {"ui_scale"}


def _coerce(key: str, value: Any) -> Any:
    """把从 settings.json 读到的值强制为期望类型；失败返回 None 表示丢弃。"""
    if key in _INT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in _BOOL_KEYS:
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            if value.lower() in ("false", "0", "no", "off"):
                return False
            return None
        return bool(value)
    if key in _FLOAT_KEYS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if key in _LIST_KEYS:
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        if isinstance(value, str):
            return [p for p in (x.strip() for x in value.split(";")) if p]
        return None
    return value


DEFAULTS: dict[str, Any] = {
    "game_dir": "",                # 游戏目录；空表示使用默认目录
    "selected_version": "",
    "download_source": "mojang",   # mojang | bmclapi | mcbbbs
    "java_path": "",               # 手动指定的 java 可执行文件；空为自动发现
    "min_memory": 2048,            # 最小堆内存 (MB)
    "max_memory": 4096,            # 最大堆内存 (MB)
    "window_width": 854,
    "window_height": 480,
    "fullscreen": False,
    "demo": False,                 # 试玩模式
    "server_address": "",          # 快速进入服务器（如 127.0.0.1:25565）
    "proxy_host": "",
    "proxy_port": 0,
    "launcher_name": LAUNCHER_NAME,
    "launcher_version": "0.2.0",
    "version_isolation": True,     # 每个版本使用独立游戏目录
    "max_download_threads": 8,
    "account_uuid": "",            # 当前使用的账号 uuid
    "microsoft_client_id": "",     # 微软登录用的 Azure 应用 client_id
    "jvm_args": "",                # 附加 JVM 参数（空格分隔）
    "game_args": "",               # 附加游戏参数（空格分隔）
    "theme": "light",
    "theme_preset": "bridge",
    "accent_color": "",             # system | light | dark
    "ui_scale": 0.0,               # 界面缩放；0 表示自动按 DPI
    "language": "zh-CN",
    "log_level": "info",           # debug | info | warn | error
    "close_after_launch": False,   # 启动游戏后关闭启动器
    "keep_launcher_open": True,    # 游戏退出后保持启动器窗口
    "download_speed_limit": 0,     # 限速 (KB/s)；0 不限
    "authlib_url": "",             # 外置登录服务器地址
    "curseforge_api_key": "",      # CurseForge API Key（可选）
    "reference_roots": [],         # 只读参考游戏目录（如 F:\\.minecraft），仅读取绝不写入
    "sandbox_dir": "",             # 试运行沙箱根目录；空表示 app_root/sandbox
    "sandbox_budget_mb": 512,      # 沙箱复制上限 (MB)，超出改用只读链接
    "allow_newer_java": True,      # 允许用更高大版本 Java 启动旧版本
    "foreign_mode": False,         # 外部实例试运行模式（启用写入闸门）
}

_LIST_KEYS = {"reference_roots"}


class Config:
    """简单线程安全的 JSON 配置。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = dict(DEFAULTS)
        self._lock = threading.Lock()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if key not in DEFAULTS:
                        continue
                    coerced = _coerce(key, value)
                    if coerced is not None:
                        self.data[key] = coerced
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            return
        coerced = _coerce(key, value)
        if coerced is None:
            return
        value = coerced
        with self._lock:
            self.data[key] = value
        self.save()

    def update(self, d: dict[str, Any]) -> None:
        with self._lock:
            self.data.update(d)
        self.save()

    def game_dir(self) -> Path:
        """解析后的游戏目录。"""
        gd = self.get("game_dir")
        return Path(gd).expanduser() if gd else default_game_dir()
