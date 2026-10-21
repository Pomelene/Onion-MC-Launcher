# -*- coding: utf-8 -*-
import json
import tempfile
from pathlib import Path

from launcher.config import Config


def test_defaults_and_coercion():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        c = Config(p)
        assert c.get("min_memory") == 2048
        c.set("min_memory", "1024")
        assert c.get("min_memory") == 1024
        c.set("max_memory", "8192")
        assert c.get("max_memory") == 8192
        c.set("ui_scale", "1.5")
        assert abs(c.get("ui_scale") - 1.5) < 1e-9
        # 未知键不保存
        c.set("unknown_key", 123)
        assert c.get("unknown_key") is None


def test_bad_type_discarded():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        p.write_text(json.dumps({"max_memory": "not-a-number"}), encoding="utf-8")
        c = Config(p)
        assert c.get("max_memory") == 4096


def test_unknown_field_ignored():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        p.write_text(json.dumps({"hack": True, "max_memory": 100}), encoding="utf-8")
        c = Config(p)
        assert c.get("hack") is None
        assert c.get("max_memory") == 100
