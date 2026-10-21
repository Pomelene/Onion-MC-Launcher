# -*- coding: utf-8 -*-
"""主题系统：模式 × 强调色 × 成品预设（参考美西螈/Modrinth 的可定制模型）。

四层结构：
1. 模式（system / light / dark / oled / retro）决定背景与文字基色；
2. 强调色决定按钮、选中态、进度条；
3. 强调色的 hover / active / soft / 前景色由 HSL 自动派生；
4. 预设方案 = 模式 + 强调色 + 少量基色覆盖，一键套用。

限制：Tk 不支持真正的圆角与逐控件透明，这里用描边与色阶近似。
"""

from .dpi import px
import colorsys
import tkinter as tk
from tkinter import ttk

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Cascadia Mono"

#: 可用的模式
MODES = ("system", "light", "dark", "oled", "retro")

#: 强调色预设（浅色/深色下都做了对比度校正）
ACCENT_PRESETS = {
    "blue": "#2f6fed",
    "pink": "#db2777",
    "green": "#16a34a",
    "purple": "#7c3aed",
    "orange": "#f97316",
    "teal": "#0d9488",
    "amber": "#f59e0b",
}

PALETTES = {
    "dark": {
        "bg": "#1e1f22", "surface": "#2b2d31", "surface2": "#383a40",
        "fg": "#e8eaed", "muted": "#9aa0a6", "border": "#3f4147",
        "danger": "#e5534b", "success": "#3fb950", "warn": "#d29922",
    },
    "light": {
        "bg": "#f5f6f8", "surface": "#ffffff", "surface2": "#eceef2",
        "fg": "#1f2328", "muted": "#6b7280", "border": "#d0d7de",
        "danger": "#d1242f", "success": "#1a7f37", "warn": "#9a6700",
    },
    "oled": {
        "bg": "#000000", "surface": "#0a0a0a", "surface2": "#151515",
        "fg": "#ededed", "muted": "#8a8a8a", "border": "#242424",
        "danger": "#f85149", "success": "#3fb950", "warn": "#d29922",
    },
    "retro": {
        "bg": "#050805", "surface": "#0b120c", "surface2": "#142016",
        "fg": "#b8ffc6", "muted": "#6f9a78", "border": "#1f3324",
        "danger": "#ff6b6b", "success": "#33ff66", "warn": "#d4ff5e",
    },
}

#: 成品预设：模式 + 强调色 + 可选基色覆盖
PRESETS = {
    "bridge": {"label": "清透科技", "mode": "light", "accent": "#176bce", "desc": "蓝白、轻盈、清晰有序",
               "bg": "#edf3fb", "surface": "#f9fcff", "surface2": "#e8f0fb",
               "fg": "#20324b", "muted": "#5d7089", "border": "#e7eef8"},
    "forest": {"label": "林间晨光", "mode": "light", "accent": "#237347", "desc": "自然、清晰、专注你的世界",
               "bg": "#f3f5f0", "surface": "#ffffff", "surface2": "#e7ede3",
               "fg": "#202b24", "muted": "#58665b", "border": "#d9e1d5"},
    "azure": {"label": "HMCL 蓝白", "mode": "light", "accent": "#3b82f6", "desc": "经典启动器配色"},
    "deep-ocean": {"label": "深海极简", "mode": "dark", "accent": "#2f6fed", "desc": "克制、工具感"},
    "sakura": {"label": "樱花晨光", "mode": "light", "accent": "#db2777", "desc": "轻盈、柔和"},
    "cyber": {"label": "赛博霓虹", "mode": "dark", "accent": "#a855f7", "desc": "高对比、未来感",
              "bg": "#0b0713", "surface": "#16101f", "surface2": "#221733",
              "fg": "#ece7f7", "border": "#33204d"},
    "oled": {"label": "OLED 墨黑", "mode": "oled", "accent": "#22c55e", "desc": "纯黑、专注"},
    "matcha": {"label": "抹茶奶绿", "mode": "light", "accent": "#16a34a", "desc": "温润、内容优先",
               "bg": "#f6f8f2", "surface": "#ffffff", "surface2": "#e8eee2",
               "fg": "#1f2a1c", "border": "#d3ddcb"},
    "amber": {"label": "琥珀夜航", "mode": "dark", "accent": "#f59e0b", "desc": "高级、暖调",
              "bg": "#15120d", "surface": "#201a12", "surface2": "#2c2418",
              "fg": "#f3ecdf", "border": "#3a2f1f"},
    "retro": {"label": "复古终端", "mode": "retro", "accent": "#33ff66", "desc": "等宽、绿磷终端"},
}


# ---------------------------------------------------------------- 颜色工具

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(int(_clamp(v, 0, 255)) for v in rgb))


def hex_to_hsl(color: str) -> tuple[float, float, float]:
    r, g, b = (v / 255.0 for v in hex_to_rgb(color))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s, l


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, _clamp(l), _clamp(s))
    return rgb_to_hex((round(r * 255), round(g * 255), round(b * 255)))


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """按比例混合两色（ratio=0 取 a，1 取 b）。"""
    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    t = _clamp(ratio)
    return rgb_to_hex((round(ra + (rb - ra) * t),
                       round(ga + (gb - ga) * t),
                       round(ba + (bb - ba) * t)))


def relative_luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    la, lb = relative_luminance(color_a), relative_luminance(color_b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def readable_fg(background: str) -> str:
    """在给定背景上选一个对比度足够的前景色。"""
    # 按钮文字通常加粗且字号偏大，3:1 即可读；这样 HMCL 蓝上会得到白字
    return "#ffffff" if contrast_ratio(background, "#ffffff") >= 3.0 else "#101010"


def derive_variants(accent: str, background: str = "#1e1f22") -> dict:
    """由一个强调色派生整套交互色。"""
    h, s, l = hex_to_hsl(accent)
    hover = hsl_to_hex(h, s, _clamp(l + 0.08))
    active = hsl_to_hex(h, s, _clamp(l - 0.08))
    soft = mix(background, accent, 0.18)
    fg = readable_fg(accent)
    # 柔和底上的文字需要比主色更深，浅色主题才够清晰
    light_bg = relative_luminance(background) > 0.5
    text = mix(accent, "#000000", 0.28) if light_bg else mix(accent, "#ffffff", 0.38)
    return {"accent": accent.lower(), "accent_hover": hover, "accent_active": active,
            "accent_soft": soft, "accent_fg": fg, "accent_text": text.lower()}


def resolve_accent(setting: str) -> str:
    """解析强调色设置：预设名 / custom:#rrggbb / system / 直接 hex。"""
    text = (setting or "").strip()
    if not text:
        return ACCENT_PRESETS["blue"]
    if text in ACCENT_PRESETS:
        return ACCENT_PRESETS[text]
    if text.startswith("custom:"):
        candidate = text[len("custom:"):].strip()
        return candidate if candidate.startswith("#") else ACCENT_PRESETS["blue"]
    if text == "system":
        return _system_accent()
    if text.startswith("#"):
        return text
    return ACCENT_PRESETS["blue"]


def _system_accent() -> str:
    """读取 Windows 强调色；失败时回退蓝色。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "ColorizationColor")
        rgb = int(value) & 0xFFFFFF
        return "#{:06x}".format(rgb)
    except Exception:  # noqa: BLE001
        return ACCENT_PRESETS["blue"]


# ---------------------------------------------------------------- 主题解析

def resolve_theme(name: str) -> str:
    """把 system 解析为明/暗；其余模式原样返回。"""
    if name in ("dark", "light", "oled", "retro"):
        return name
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except Exception:  # noqa: BLE001
        return "light"


def resolve_palette(mode: str = "system", accent: str = "", preset: str = "") -> dict:
    """合成最终配色：模式基色 + 预设覆盖 + 强调色派生。"""
    spec = PRESETS.get(preset or "", {})
    base_mode = spec.get("mode") or mode or "system"
    colors = dict(PALETTES[resolve_theme(base_mode)])
    for token in ("bg", "surface", "surface2", "fg", "muted", "border"):
        if spec.get(token):
            colors[token] = spec[token]
    chosen = spec.get("accent") or accent or ACCENT_PRESETS["blue"]
    colors.update(derive_variants(resolve_accent(chosen), colors["bg"]))
    colors["mode"] = resolve_theme(base_mode)
    colors["preset"] = preset
    # 侧栏比内容区略深/略浅一档，营造 HMCL 那种“导航 + 白色内容区”的层次
    colors["sidebar"] = mix(colors["surface"], colors["bg"], .45)
    colors["hover"] = mix(colors["surface"], colors["accent"], 0.06)
    colors["hero"] = mix(colors["surface"], colors["accent"], 0.075)
    colors["art_line"] = mix(colors["surface"], colors["accent"], 0.19)
    return colors


def palette(name: str, accent: str = "", preset: str = "") -> dict:
    """向后兼容：按模式名取配色。"""
    return resolve_palette(name, accent, preset)


def apply_dpi(root: tk.Misc, ui_scale: float) -> float:
    """按倍率缩放 Tk 全局尺寸；0 表示自动（按 96 DPI 基准）。"""
    try:
        dpi = root.winfo_fpixels("1i")
        auto = round(dpi / 72.0, 3) if dpi else 1.0
    except Exception:  # noqa: BLE001
        auto = 1.0
    scale = float(ui_scale) if ui_scale and ui_scale > 0 else auto
    scale = max(0.75, min(scale, 2.5))
    try:
        root.tk.call("tk", "scaling", scale)
    except Exception:  # noqa: BLE001
        pass
    return scale


def apply_style(root: tk.Misc, name: str, accent: str = "", preset: str = "") -> dict:
    """配置 ttk 样式并返回最终 palette。"""
    p = resolve_palette(name, accent, preset)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    family = MONO_FAMILY if p.get("mode") == "retro" else FONT_FAMILY
    base_font = (family, 10)
    style.configure(".", background=p["bg"], foreground=p["fg"],
                    font=base_font, borderwidth=0, relief="flat")
    style.configure("TFrame", background=p["bg"])
    style.configure("Card.TFrame", background=p["surface"])
    style.configure("TLabel", background=p["bg"], foreground=p["fg"], font=base_font)
    style.configure("Card.TLabel", background=p["surface"], foreground=p["fg"])
    style.configure("Title.TLabel", background=p["bg"], foreground=p["fg"],
                    font=(family, 18, "bold"))
    style.configure("H1.TLabel", background=p["bg"], foreground=p["fg"],
                    font=(family, 13, "bold"))
    style.configure("Sub.TLabel", background=p["bg"], foreground=p["muted"],
                    font=(family, 9))
    style.configure("Card.Sub.TLabel", background=p["surface"], foreground=p["muted"],
                    font=(family, 9))
    style.configure("TButton", background=p["surface"], foreground=p["fg"],
                    font=base_font, borderwidth=0, padding=(10, 6))
    style.map("TButton",
              background=[("active", p["surface2"]), ("pressed", p["surface2"])],
              foreground=[("disabled", p["muted"])])
    style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_fg"],
                    font=(family, 10, "bold"), borderwidth=0, padding=(14, 7))
    style.map("Accent.TButton", background=[("active", p["accent_hover"]),
              ("pressed", p.get("accent_active", p["accent_hover"]))])
    style.configure("Danger.TButton", background=p["danger"], foreground="#ffffff",
                    borderwidth=0, padding=(10, 6))
    style.map("Danger.TButton", background=[("active", p["danger"])])
    style.configure("TEntry", fieldbackground=p["surface"], foreground=p["fg"],
                    insertcolor=p["fg"], bordercolor=p["border"], lightcolor=p["border"],
                    darkcolor=p["border"], padding=5)
    style.configure("TCombobox", fieldbackground=p["surface"], background=p["surface"],
                    foreground=p["fg"], arrowcolor=p["fg"], bordercolor=p["border"],
                    lightcolor=p["border"], darkcolor=p["border"], padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", p["surface"])],
              foreground=[("readonly", p["fg"])])
    style.configure("Horizontal.TProgressbar", background=p["accent"],
                    troughcolor=p["surface2"], borderwidth=0, thickness=px(8))
    style.configure("Vertical.TScrollbar", background=p["surface2"], troughcolor=p["bg"],
                    arrowcolor=p["muted"], borderwidth=0)
    style.configure("TCheckbutton", background=p["bg"], foreground=p["fg"], font=base_font)
    style.map("TCheckbutton", background=[("active", p["bg"])])
    style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                    foreground=p["fg"], rowheight=px(26), borderwidth=0)
    style.map("Treeview", background=[("selected", p["accent"])],
              foreground=[("selected", p["accent_fg"])])
    root.configure(background=p["bg"])
    return p
