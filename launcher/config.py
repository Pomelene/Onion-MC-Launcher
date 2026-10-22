# -*- coding: utf-8 -*-
"""全局配置读写，默认使用 onionmcl.json 的 settings 分区。

配置以 JSON 保存、结构平坦，未知字段自动忽略；
所有字段均有默认值，线程安全。
"""

from .storage import is_portable,read_section,write_section
import json
import threading
import tempfile
from pathlib import Path
from typing import Any

from .paths import default_game_dir,LAUNCHER_NAME,LAUNCHER_VERSION
from .secrets import protect,unprotect,SecretStorageError

#: 需要按类型强制的键（避免 settings.json 手工编辑引入错类型）
_INT_KEYS = {"min_memory", "max_memory", "window_width", "window_height",
             "proxy_port", "max_download_threads", "download_speed_limit",
             "sandbox_budget_mb", "text_transparency", "ui_transparency", "background_transparency"}
_BOOL_KEYS = {"fullscreen", "demo", "version_isolation",
              "close_after_launch", "keep_launcher_open",
              "allow_newer_java", "foreign_mode", "auto_memory", "show_launch_logs"}
_FLOAT_KEYS = {"ui_scale"}


def _coerce(key: str, value: Any) -> Any:
    """把从 settings.json 读到的值强制为期望类型；失败返回 None 表示丢弃。"""
    if key=='color_mode':return value if value in ('dark','light') else 'dark'
    if key=='background_mode':return value if value in ('fill','fit','stretch','center','tile') else 'fill'
    if key in _INT_KEYS:
        try:
            number=int(value)
            if key in ('text_transparency','ui_transparency','background_transparency'):
                return max(0,min(70 if key=='text_transparency' else 100,number))
            return number
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
    "auto_memory": False,          # 保留已有手动设置，用户可切换自动分配
    "show_launch_logs": False,
    "background_image": "",
    "window_width": 854,
    "window_height": 480,
    "fullscreen": False,
    "demo": False,                 # 试玩模式
    "server_address": "",          # 快速进入服务器（如 127.0.0.1:25565）
    "proxy_host": "",
    "proxy_port": 0,
    "launcher_name": LAUNCHER_NAME,
    "launcher_version": LAUNCHER_VERSION,
    "version_isolation": True,     # 每个版本使用独立游戏目录
    "max_download_threads": 8,
    "account_uuid": "",            # 当前使用的账号 uuid
    "microsoft_client_id": "",     # 微软登录用的 Azure 应用 client_id
    "jvm_args": "",                # 附加 JVM 参数（空格分隔）
    "game_args": "",               # 附加游戏参数（空格分隔）
    "theme": "light",
    "theme_preset": "bridge",
    "accent_color": "#cebafa",      # 可点击设置文字的高亮色
    "color_mode": "dark",          # Qt 深浅模式；保留旧 theme 字段用于历史界面
    "text_transparency": 0,         # 0 为不透明；最多 70，保留文字可读性
    "ui_transparency": 0,           # 面板底色透明度，不改变整窗或文字透明度
    "background_transparency": 0,   # 首页图片/装饰透明度
    "background_mode": "fill",     # fill / fit / stretch / center / tile
    "ui_animations": True,        # 页面过渡与控件动效；关闭可减少动态效果
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
        self._locked_secret_settings=None
        self.load()

    def load(self) -> None:
        if not self.path.exists() and not is_portable(self.path):
            return
        try:
            loaded = read_section(self.path,"settings")
            if isinstance(loaded, dict):
                envelope=loaded.get('protected_settings')
                if envelope is not None:
                    loaded['curseforge_api_key']=''
                    try:loaded['curseforge_api_key']=unprotect(envelope).get('curseforge_api_key','')
                    except SecretStorageError:self._locked_secret_settings=envelope
                for key, value in loaded.items():
                    if key not in DEFAULTS:
                        continue
                    coerced = _coerce(key, value)
                    if coerced is not None:
                        self.data[key] = coerced
                if envelope is None and self.data.get('curseforge_api_key'):self.save()
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload=dict(self.data);secret=payload.pop('curseforge_api_key','')
        if secret:payload['protected_settings']=protect({'curseforge_api_key':secret})
        elif self._locked_secret_settings is not None:payload['protected_settings']=self._locked_secret_settings
        if is_portable(self.path):
            write_section(self.path,"settings",payload)
            return
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,
                                             prefix='.onion-settings-',delete=False) as output:
                temporary=Path(output.name);json.dump(payload,output,ensure_ascii=False,indent=2)
            temporary.replace(self.path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)

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
