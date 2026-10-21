# -*- coding: utf-8 -*-
"""为 UI 生成截图与主题画廊（docs/screens）。"""

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 让截图坐标与屏幕物理像素一致；默认 150% 缩放下窗口会超出屏幕
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass

from PIL import Image, ImageDraw, ImageGrab

from launcher.ui.app import App

OUT = ROOT / "docs" / "screens"


def _client_bbox(app) -> tuple[int, int, int, int]:
    """用 Win32 客户端矩形取窗口内容区（绕开 DPI 缩放与窗口阴影）。"""
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = app.winfo_id()
        point = wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point))
        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
        if rect.right > 100 and rect.bottom > 100:
            return (point.x, point.y, point.x + rect.right, point.y + rect.bottom)
    except Exception:  # noqa: BLE001
        pass
    x, y = app.winfo_rootx(), app.winfo_rooty()
    return (x, y, x + app.winfo_width(), y + app.winfo_height())


def shot(app, page: str, name: str, prep=None):
    if prep:
        prep()
    app.switch_page(page)
    app.update_idletasks()
    app.update()
    time.sleep(0.35)
    w, h = app.winfo_width(), app.winfo_height()
    img = ImageGrab.grab(_client_bbox(app))
    if img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{name}.png"
    img.save(target)
    print(target, img.size)
    return img


def gallery(images: list[tuple[str, Image.Image]], name: str, columns: int = 2) -> None:
    """把多张截图拼成带标题的画廊。"""
    if not images:
        return
    thumb_w = 560
    ratio = thumb_w / images[0][1].width
    thumb_h = int(images[0][1].height * ratio)
    label_h = 34
    rows = (len(images) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * (thumb_w + 16) + 16,
                                rows * (thumb_h + label_h + 16) + 16), (16, 17, 20))
    draw = ImageDraw.Draw(canvas)
    for index, (title, image) in enumerate(images):
        col, row = index % columns, index // columns
        x = 16 + col * (thumb_w + 16)
        y = 16 + row * (thumb_h + label_h + 16)
        draw.text((x + 4, y + 8), title, fill=(232, 234, 237))
        canvas.paste(image.resize((thumb_w, thumb_h)), (x, y + label_h))
    target = OUT / f"{name}.png"
    canvas.save(target)
    print(target, canvas.size)


def main() -> None:
    app = App()
    original = {key: app.config_obj.get(key) for key in
                ("theme", "theme_preset", "accent_color", "ui_scale")}
    # 文档截图统一按 96 DPI 排版，窗口才能完整落在屏幕内
    app.config_obj.set("ui_scale", 1.333)
    app.apply_theme()
    app.geometry("1240x780+20+20")
    app.update_idletasks()

    # 常规页面（深色）
    app.config_obj.set("theme", "dark")
    app.config_obj.set("theme_preset", "")
    app.config_obj.set("accent_color", "blue")
    app.apply_theme()
    shot(app, "home", "home-dark")
    shot(app, "versions", "versions-dark", prep=lambda: app.set_selected_version("1.20.4"))
    shot(app, "download", "download-dark")
    shot(app, "mods", "mods-dark",
         prep=lambda: app.set_selected_version("fabric-loader-0.19.5-1.20.4"))
    shot(app, "worlds", "worlds-dark")
    shot(app, "logs", "logs-dark")
    shot(app, "settings", "settings-dark")

    # 浅色（默认 HMCL 蓝白）
    app.config_obj.set("theme", "light")
    app.config_obj.set("theme_preset", "azure")
    app.config_obj.set("accent_color", "")
    app.apply_theme()
    shot(app, "home", "home-light")
    shot(app, "versions", "versions-light", prep=lambda: app.set_selected_version("1.20.4"))
    shot(app, "settings", "settings-light")
    for category in ("game", "java", "appearance", "download"):
        shot(app, "settings", f"settings-{category}",
             prep=lambda c=category: app.pages["settings"]._select(c))

    # 七套预设
    from launcher.ui.theme import PRESETS

    images = []
    for key, spec in PRESETS.items():
        app.config_obj.set("theme", spec["mode"])
        app.config_obj.set("theme_preset", key)
        app.config_obj.set("accent_color", "")
        app.apply_theme()
        img = shot(app, "home", f"preset-{key}")
        images.append((f"{spec['label']} / {key}", img))
    gallery(images, "theme-gallery", columns=2)
    for key, value in original.items():
        app.config_obj.set(key, value)
    app.config_obj.save()
    app.destroy()


if __name__ == "__main__":
    main()