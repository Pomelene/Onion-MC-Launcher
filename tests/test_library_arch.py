# -*- coding: utf-8 -*-
"""库的 arch 占位符替换（1.8.9 Twitch 原生库回归）。"""

from launcher import libraries
from launcher.libraries import Library


def _with_arch(bits, fn):
    old = libraries.arch_bits
    libraries.arch_bits = lambda: bits
    try:
        return fn()
    finally:
        libraries.arch_bits = old


def test_arch_placeholder_64():
    lib = Library.from_json({
        "name": "tv.twitch:twitch-platform:6.5",
        "natives": {"windows": "natives-windows-${arch}"},
    })
    def run():
        assert lib.native_classifier() == "natives-windows-64"
        assert lib.native_path() == (
            "tv/twitch/twitch-platform/6.5/twitch-platform-6.5-natives-windows-64.jar")
    _with_arch("64", run)


def test_arch_placeholder_32():
    lib = Library.from_json({
        "name": "tv.twitch:twitch-platform:6.5",
        "natives": {"windows": "natives-windows-${arch}"},
    })
    def run():
        assert lib.native_classifier() == "natives-windows-32"
    _with_arch("32", run)


def test_no_placeholder_untouched():
    lib = Library.from_json({
        "name": "org.lwjgl:lwjgl:3.3.1",
        "natives": {"windows": "natives-windows"},
    })
    assert lib.native_classifier() == "natives-windows"
