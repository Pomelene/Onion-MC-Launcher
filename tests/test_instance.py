# -*- coding: utf-8 -*-
"""实例元数据测试：名称、分组、游玩时长与持久化。"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher.instance import DEFAULT_GROUP, InstanceStore


def test_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        store = InstanceStore(Path(tmp) / "instances.json")
        meta = store.get("1.20.4")
        assert meta.display_name == "1.20.4"
        assert meta.group == DEFAULT_GROUP
        assert meta.play_time_text() == "0 分钟"


def test_update_and_reload():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "instances.json"
        store = InstanceStore(path)
        store.update("1.20.4", name="原版生存", group="长期档", notes="只装优化模组")
        again = InstanceStore(path)
        meta = again.get("1.20.4")
        assert meta.name == "原版生存"
        assert meta.display_name == "原版生存"
        assert meta.group == "长期档"
        assert "优化" in meta.notes


def test_launch_and_play_time():
    with tempfile.TemporaryDirectory() as tmp:
        store = InstanceStore(Path(tmp) / "instances.json")
        store.record_launch("fabric", when=1_700_000_000)
        store.add_play_time("fabric", 3600)
        store.add_play_time("fabric", 1800)
        meta = store.get("fabric")
        assert meta.launch_count == 1
        assert meta.last_played == 1_700_000_000
        assert "1 小时 30 分钟" == meta.play_time_text()


def test_groups_and_remove():
    with tempfile.TemporaryDirectory() as tmp:
        store = InstanceStore(Path(tmp) / "instances.json")
        store.update("a", group="整合包")
        store.update("b", group="整合包")
        store.update("c", group=  "原版")
        assert store.groups() == ["原版", "整合包"]
        store.remove("a")
        assert store.get("a").display_name == "a"