# -*- coding: utf-8 -*-
"""冒烟：启动刚装好的 OptiFine 版本，确认能进开始界面。"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher.accounts import offline_uuid
from launcher.config import Config
from launcher.java import pick_java
from launcher.launch import Account, LaunchSettings, launch
from launcher.paths import default_settings_path
from launcher.repository import GameRepository
from launcher.windowwatch import capture_window, kill_tree, screenshot_stats, wait_for_game_window

VID = "1.20.4-OptiFine_HD_U_I7"
config = Config(default_settings_path())
repo = GameRepository(config)
rv = repo.install(VID)
print("main_class:", rv.main_class, "| client jar:", repo.client_jar_path(rv))
print("optifine libs:", [str(p) for p in (repo.libraries_dir / "optifine").rglob("*.jar")])
java = pick_java(rv.java_major or 17)
print("java:", java.major if java else None)
proc = launch(repo, rv, Account("Steve", offline_uuid("Steve")),
              LaunchSettings(max_memory=2048), str(java.path))
info = wait_for_game_window(proc.proc.pid, timeout=150)
if not info:
    print("NO WINDOW")
    kill_tree(proc.proc.pid)
    sys.exit(1)
print("window:", info.title, info.rect)
shot = ROOT / "docs" / "screens" / "optifine-1.20.4.png"
capture_window(info.hwnd, shot)
print("shot:", shot, screenshot_stats(shot))
time.sleep(2)
kill_tree(proc.proc.pid)
print("done")