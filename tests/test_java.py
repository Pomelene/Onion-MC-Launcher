# -*- coding: utf-8 -*-
import os

from launcher.java import JAVA_COMPONENTS, probe_java, runtime_dir


def test_java_components_mapping():
    assert JAVA_COMPONENTS[8] == "jre-legacy"
    assert JAVA_COMPONENTS[16] == "java-runtime-alpha"
    assert JAVA_COMPONENTS[17] == "java-runtime-beta"
    assert JAVA_COMPONENTS[21] == "java-runtime-delta"
    assert JAVA_COMPONENTS[25] == "java-runtime-epsilon"


def test_probe_workspace_java17():
    # 若本地 runtime 已下载则探测应为 17（否则跳过，不做断言）
    exe = runtime_dir("java-runtime-beta") / "bin" / ("java.exe" if os.name == "nt" else "java")
    if exe.exists():
        info = probe_java(exe)
        assert info is not None and info.major == 17


def test_probe_invalid_returns_none():
    from pathlib import Path
    assert probe_java(Path("Z:/不存在/java.exe")) is None
