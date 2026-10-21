# -*- coding: utf-8 -*-
"""主题系统测试：对比度、派生色与强调色解析。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher.ui.theme import (ACCENT_PRESETS, PRESETS, contrast_ratio, derive_variants,
                               resolve_accent, resolve_palette)


def test_all_presets_readable():
    for key, spec in PRESETS.items():
        p = resolve_palette(spec["mode"], preset=key)
        assert contrast_ratio(p["fg"], p["bg"]) >= 4.5, f"{key} 正文对比度不足"
        assert contrast_ratio(p["accent_fg"], p["accent"]) >= 3.0, f"{key} 按钮对比度不足"


def test_palette_tokens_present():
    p = resolve_palette("dark", "blue")
    for token in ("bg", "surface", "surface2", "fg", "muted", "border",
                  "accent", "accent_hover", "accent_active", "accent_soft", "accent_fg"):
        assert p.get(token), token


def test_derive_variants_changes_lightness():
    variants = derive_variants("#2f6fed", "#1e1f22")
    assert variants["accent_hover"] != variants["accent"]
    assert variants["accent_active"] != variants["accent"]
    assert variants["accent_soft"] not in ("#2f6fed", "#1e1f22")


def test_resolve_accent_forms():
    assert resolve_accent("pink") == ACCENT_PRESETS["pink"]
    assert resolve_accent("custom:#123456") == "#123456"
    assert resolve_accent("#abcdef") == "#abcdef"
    assert resolve_accent("").startswith("#")


def test_unknown_preset_falls_back():
    p = resolve_palette("dark", preset="not-exist")
    assert p["bg"] == "#1e1f22"