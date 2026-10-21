"""原生像素渲染与逻辑尺寸换算，避免 Windows 对整个窗口进行位图放大。"""
import sys

_factor = 1.0


def enable_high_dpi():
    global _factor
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # Tk 8.6 使用系统 DPI；跨显示器仍保留系统的尺寸兼容行为。
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        ctypes.windll.user32.SetProcessDPIAware()
    try:
        _factor = ctypes.windll.user32.GetDpiForSystem() / 96.0
    except (OSError, AttributeError):
        _factor = 1.0


def px(value):
    if isinstance(value, (tuple, list)):
        return tuple(px(item) for item in value)
    return round(value * _factor)


def geometry(value):
    width, height = value.split("x")
    return f"{px(int(width))}x{px(int(height))}"
