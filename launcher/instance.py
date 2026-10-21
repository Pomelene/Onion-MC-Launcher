# -*- coding: utf-8 -*-
"""实例元数据：自定义名称、分组、备注、游玩时长。

HMCL/PCL 都把“版本”当作“实例”来管理：除了版本 id，还有玩家可编辑的展示信息。
这里把展示信息与启动配置分开存：
- config/instances.json：名称/分组/备注/最后游玩/累计时长；
- config/version_settings.json：Java、内存、窗口、参数等启动覆盖。
版本被删除时，两边的数据都会清理，避免残留。
"""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_GROUP = "默认"


def default_instance_name(version: str, loader: str = 'vanilla') -> str:
    names={'vanilla':'原版','fabric':'Fabric','forge':'Forge','neoforge':'NeoForge','quilt':'Quilt','optifine':'OptiFine'}
    return f"{version}-{names.get(loader.lower(),loader)}"


def _now() -> float:
    return time.time()


@dataclass
class InstanceMeta:
    """一个实例的展示信息。"""

    version_id: str
    name: str = ""
    group: str = DEFAULT_GROUP
    notes: str = ""
    icon: str = ""
    last_played: float = 0.0
    play_seconds: float = 0.0
    launch_count: int = 0

    @property
    def display_name(self) -> str:
        return self.name.strip() or self.version_id

    def last_played_text(self) -> str:
        if not self.last_played:
            return "从未启动"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.last_played))

    def play_time_text(self) -> str:
        total = int(self.play_seconds)
        if total <= 0:
            return "0 分钟"
        hours, minutes = divmod(total // 60, 60)
        if hours:
            return f"{hours} 小时 {minutes} 分钟"
        return f"{minutes} 分钟"


class InstanceStore:
    """instances.json 的读写（原子落盘、线程安全）。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            from .paths import app_root

            path = app_root() / "config" / "instances.json"
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, InstanceMeta] = {}
        self.load()

    # ------------------------------------------------------------ 持久化

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        data: dict[str, InstanceMeta] = {}
        for version_id, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            data[str(version_id)] = InstanceMeta(
                version_id=str(version_id),
                name=str(entry.get("name") or ""),
                group=str(entry.get("group") or DEFAULT_GROUP),
                notes=str(entry.get("notes") or ""),
                icon=str(entry.get("icon") or ""),
                last_played=float(entry.get("last_played") or 0),
                play_seconds=float(entry.get("play_seconds") or 0),
                launch_count=int(entry.get("launch_count") or 0),
            )
        self._data = data

    def save(self) -> None:
        payload = {
            meta.version_id: {
                "name": meta.name,
                "group": meta.group,
                "notes": meta.notes,
                "icon": meta.icon,
                "last_played": meta.last_played,
                "play_seconds": round(meta.play_seconds, 1),
                "launch_count": meta.launch_count,
            }
            for meta in self._data.values()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------ 查询

    def get(self, version_id: str) -> InstanceMeta:
        with self._lock:
            return self._data.get(version_id) or InstanceMeta(version_id=version_id)

    def display_name(self, version_id: str) -> str:
        return self.get(version_id).display_name

    def all(self) -> list[InstanceMeta]:
        with self._lock:
            return list(self._data.values())

    def groups(self) -> list[str]:
        names = {meta.group or DEFAULT_GROUP for meta in self.all()}
        return sorted(names)

    # ------------------------------------------------------------ 更新

    def update(self, version_id: str, **fields) -> InstanceMeta:
        allowed = {"name", "group", "notes", "icon"}
        with self._lock:
            meta = self._data.get(version_id) or InstanceMeta(version_id=version_id)
            for key, value in fields.items():
                if key in allowed:
                    setattr(meta, key, str(value or "").strip())
            if not meta.group:
                meta.group = DEFAULT_GROUP
            self._data[version_id] = meta
        self.save()
        return meta

    def record_launch(self, version_id: str, when: Optional[float] = None) -> InstanceMeta:
        with self._lock:
            meta = self._data.get(version_id) or InstanceMeta(version_id=version_id)
            meta.last_played = float(when if when is not None else _now())
            meta.launch_count += 1
            self._data[version_id] = meta
        self.save()
        return meta

    def add_play_time(self, version_id: str, seconds: float) -> InstanceMeta:
        seconds = max(0.0, float(seconds))
        with self._lock:
            meta = self._data.get(version_id) or InstanceMeta(version_id=version_id)
            meta.play_seconds += seconds
            self._data[version_id] = meta
        self.save()
        return meta

    def remove(self, version_id: str) -> None:
        with self._lock:
            self._data.pop(version_id, None)
        self.save()
