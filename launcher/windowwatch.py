# -*- coding: utf-8 -*-
"""游戏窗口检测与截图判活（纯 ctypes，无第三方依赖）。

试运行需要自动回答一个问题：游戏是否真的进到了开始界面？
这里用三层证据：
1. 进程存活；
2. 按进程号找到可见窗口，标题包含 Minecraft；
3. 截图像素统计（唯一色数、平均亮度）排除纯黑/白屏。
"""

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

IS_WINDOWS = os.name == "nt"


@dataclass
class WindowInfo:
    """一个顶层窗口。"""

    hwnd: int
    title: str
    pid: int
    visible: bool
    rect: tuple[int, int, int, int]  # (left, top, right, bottom)

    @property
    def width(self) -> int:
        return max(0, self.rect[2] - self.rect[0])

    @property
    def height(self) -> int:
        return max(0, self.rect[3] - self.rect[1])


def list_windows() -> list[WindowInfo]:
    """枚举所有带标题的顶层窗口。"""
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32
    result: list[WindowInfo] = []
    proc_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        result.append(WindowInfo(
            hwnd=int(hwnd), title=buf.value, pid=int(pid.value),
            visible=bool(user32.IsWindowVisible(hwnd)),
            rect=(rect.left, rect.top, rect.right, rect.bottom),
        ))
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return result


def find_windows_for_pid(pid: int) -> list[WindowInfo]:
    return [w for w in list_windows() if w.pid == int(pid)]


def wait_for_game_window(pid: int, timeout: float = 180.0, interval: float = 0.4,
                         hints: tuple[str, ...] = ("minecraft",)) -> Optional[WindowInfo]:
    """等待该进程出现标题匹配的游戏窗口；超时返回 None。

    优先返回可见且尺寸合理的窗口；找不到时退回任意匹配窗口。
    """
    deadline = time.time() + float(timeout)
    fallback: Optional[WindowInfo] = None
    while time.time() < deadline:
        for win in find_windows_for_pid(pid):
            title = win.title.lower()
            if not any(h in title for h in hints):
                continue
            if win.visible and win.width > 200 and win.height > 150:
                return win
            if fallback is None:
                fallback = win
        time.sleep(interval)
    return fallback


def capture_window(hwnd: int, out_path: Path) -> bool:
    """截取窗口区域到 PNG（需要 Pillow，仅用于测试/报告）。"""
    if not IS_WINDOWS:
        return False
    wins = [w for w in list_windows() if w.hwnd == int(hwnd)]
    if not wins:
        return False
    win = wins[0]
    if win.width < 8 or win.height < 8:
        return False
    try:
        from PIL import ImageGrab
    except ImportError:
        return False
    try:
        image = ImageGrab.grab(win.rect)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
        return True
    except OSError:
        return False


def screenshot_stats(path: Path) -> dict:
    """统计截图：唯一色数、平均亮度、暗像素比例，用于排除黑屏。"""
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "reason": "缺少 Pillow"}
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            colors = rgb.getcolors(maxcolors=1_000_000)
            unique = len(colors) if colors is not None else 1_000_000
            gray = rgb.convert("L")
            pixels = list(gray.getdata())
    except (OSError, ValueError) as exc:
        return {"ok": False, "reason": f"读取截图失败：{exc}"}
    if not pixels:
        return {"ok": False, "reason": "空截图"}
    brightness = sum(pixels) / len(pixels)
    dark = sum(1 for p in pixels if p < 8) / len(pixels)
    ok = unique >= 64 and brightness > 8.0 and dark < 0.98
    return {"ok": ok, "unique": unique, "brightness": round(brightness, 2),
            "dark_ratio": round(dark, 3)}


def kill_tree(pid: int) -> None:
    """结束进程及其子进程（Windows）。"""
    if not IS_WINDOWS:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))],
                       capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass
