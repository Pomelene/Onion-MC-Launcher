# -*- coding: utf-8 -*-
"""按版本独立设置。

每个版本的覆盖项保存在 onionmcl.json 的 version_settings 分区，键为版本 id，
值为可选的局部配置；未设置项回退到全局配置。
"""

from .storage import is_portable,read_section,write_section
import json
import threading
from pathlib import Path
from typing import Any


#: 允许的局部覆盖键及其期望类型
SCHEMA: dict[str, type] = {
    "java_path": str,
    "min_memory": int,
    "max_memory": int,
    "auto_memory": bool,
    "jvm_args": str,
    "game_args": str,
    "width": int,
    "height": int,
    "fullscreen": bool,
    "isolate": bool,
    "server_address": str,
}


class VersionSettingsStore:
    """版本级设置的读写与合并。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists() and not is_portable(self.path):
            return
        try:
            raw = read_section(self.path,"version_settings")
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        cleaned: dict[str, dict] = {}
        for vid, overrides in raw.items():
            if not isinstance(overrides, dict):
                continue
            entry = {}
            for key, typ in SCHEMA.items():
                value = overrides.get(key)
                if value is None:
                    continue
                try:
                    entry[key] = typ(value) if typ is not bool else bool(value)
                except (TypeError, ValueError):
                    continue
            cleaned[vid] = entry
        self._data = cleaned

    def save(self) -> None:
        if is_portable(self.path):
            write_section(self.path,"version_settings",self._data)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, version_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get(version_id, {}))

    def set(self, version_id: str, overrides: dict[str, Any]) -> None:
        entry = {}
        for key, typ in SCHEMA.items():
            value = overrides.get(key)
            if value is None or value == "" and typ is not str:
                continue
            try:
                entry[key] = typ(value) if typ is not bool else bool(value)
            except (TypeError, ValueError):
                continue
        with self._lock:
            self._data[version_id] = entry
        self.save()

    def clear(self, version_id: str) -> None:
        with self._lock:
            self._data.pop(version_id, None)
        self.save()

    def resolve(self, version_id: str, global_cfg) -> dict[str, Any]:
        """把全局配置与版本覆盖合并，返回可直接使用的启动配置。"""
        over = self.get(version_id)
        result = {
            "java_path": over.get("java_path", global_cfg.get("java_path")) or "",
            "min_memory": over.get("min_memory", global_cfg.get("min_memory", 2048)),
            "max_memory": over.get("max_memory", global_cfg.get("max_memory", 4096)),
            "jvm_args": over.get("jvm_args", global_cfg.get("jvm_args", "")),
            "game_args": over.get("game_args", global_cfg.get("game_args", "")),
            "width": over.get("width", global_cfg.get("window_width", 854)),
            "height": over.get("height", global_cfg.get("window_height", 480)),
            "fullscreen": over.get("fullscreen", global_cfg.get("fullscreen", False)),
            "isolate": over.get("isolate", global_cfg.get("version_isolation", False)),
            "server_address": over.get("server_address", global_cfg.get("server_address", "")),
        }
        if over.get('auto_memory', global_cfg.get('auto_memory', False)):
            from .memory import recommended_memory
            result['min_memory'], result['max_memory'] = recommended_memory()
        return result
