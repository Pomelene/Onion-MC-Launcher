"""Launcher geometry in Qt logical pixels (already adjusted for screen DPI)."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication


def fitted_size(available, width=0, height=0):
    """Use a compact first-run size; constrain saved sizes to today's screen."""
    bounds = QSize(max(1, available.width()), max(1, available.height()))
    minimum = QSize(min(900, bounds.width()), min(600, bounds.height()))
    if width <= 0 or height <= 0:
        width = min(1280, round(bounds.width() * .82))
        height = min(800, round(bounds.height() * .82))
    size = QSize(max(minimum.width(), min(width, bounds.width())),
                 max(minimum.height(), min(height, bounds.height())))
    return minimum, size


def restore_window_size(window, config):
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is None:
        return
    area = screen.availableGeometry()
    minimum, size = fitted_size(area.size(), config.get('launcher_window_width', 0),
                               config.get('launcher_window_height', 0))
    window.setMinimumSize(minimum)
    window.resize(size)
    window.move(area.x() + (area.width() - size.width()) // 2,
                area.y() + (area.height() - size.height()) // 2)
    if config.get('launcher_window_maximized', False):
        window.setWindowState(window.windowState() | Qt.WindowState.WindowMaximized)


def remember_window_size(window, config):
    # A maximized/minimized window must not replace its normal restore size.
    normal = window.normalGeometry() if window.isMaximized() or window.isMinimized() or window.isFullScreen() else window.geometry()
    if normal.isValid():
        config.update({'launcher_window_width': normal.width(),
                       'launcher_window_height': normal.height(),
                       'launcher_window_maximized': bool(window.windowState() & Qt.WindowState.WindowMaximized)})
