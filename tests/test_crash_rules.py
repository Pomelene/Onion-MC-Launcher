# -*- coding: utf-8 -*-
"""崩溃规则测试：常见异常都能匹配到合适的中文结论。"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher.crash import diagnose, diagnose_file


def test_out_of_memory():
    result = diagnose("java.lang.OutOfMemoryError: Java heap space\n\tat net.minecraft...")
    assert result["id"] == "out_of_memory"


def test_java_too_old():
    text = "java.lang.UnsupportedClassVersionError: net/fabricmc/loader/impl/launch/knot/KnotClient has been compiled by a more recent version"
    assert diagnose(text)["id"] == "java_too_old"


def test_missing_dependency():
    text = "Missing or unsupported mandatory dependencies:\n\tMod ID: x, Requested: y"
    assert diagnose(text)["id"] == "missing_dependency"


def test_duplicate_mods():
    assert diagnose("Duplicate mods found for modid create")["id"] == "duplicate_mods"


def test_opengl():
    assert diagnose("Pixel format not accelerated")["id"] == "opengl"


def test_unknown_fallback():
    result = diagnose("something completely normal here")
    assert result["id"] == "unknown" and result["advice"]


def test_diagnose_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "crash-report.txt"
        path.write_text("Description: Rendering overlay\nA fatal error has been detected by the Java Runtime Environment\n",
                        encoding="utf-8")
        result = diagnose_file(path)
        assert result["id"] == "native_crash"
        assert result["description"] == "Rendering overlay"