# -*- coding: utf-8 -*-
import time
import tempfile
from pathlib import Path

from launcher.crash import latest_crash_report, parse_crash

REPORT = """---- Minecraft Crash Report ----
// why
Time: 2026-01-01 12:00:00
Description: Unexpected error

java.lang.NullPointerException: boom
\tat net.minecraft.Test.main(Test.java:1)

-- Suspected Mods --
badmod-1.0.jar
another-2.0.jar
-- END --
Java Version: 17.0.15, Oracle Corporation
"""


def test_parse_crash():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "crash-x.txt"
        p.write_text(REPORT, encoding="utf-8")
        info = parse_crash(p)
        assert "NullPointerException" in info["exception"]
        assert info["description"] == "Unexpected error"
        assert info["java"].startswith("17")
        assert "badmod-1.0.jar" in info["suspected"]


def test_latest_crash_report():
    with tempfile.TemporaryDirectory() as d:
        run = Path(d)
        cd = run / "crash-reports"
        cd.mkdir()
        old = cd / "crash-old.txt"
        old.write_text(REPORT, encoding="utf-8")
        time.sleep(0.05)
        new = cd / "crash-new.txt"
        new.write_text(REPORT, encoding="utf-8")
        assert latest_crash_report(run).name == "crash-new.txt"
        assert latest_crash_report(run, since_ts=time.time() + 10) is None
