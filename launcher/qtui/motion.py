"""Short, interruptible motion without moving layouts or delaying actions.

Page changes fade a single in-memory image of the previous surface over the
live destination. Widgets keep their focus, scroll position and native painting.
No desktop capture, graphics effects on scroll areas, or continuous timers.
"""
from contextlib import contextmanager
from functools import wraps

from PySide6.QtCore import QObject, QEvent, Qt, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QPushButton


PAGE_DURATION = 180
HOVER_DURATION = 140
PRESS_DURATION = 80


def motion_enabled(widget):
    config = getattr(widget.window(), 'config_obj', None)
    return bool(config.get('ui_animations')) if config else True


class SnapshotLayer(QWidget):
    def __init__(self, parent, pixmap):
        super().__init__(parent)
        self.pixmap = pixmap
        self.opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(parent.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(self.opacity)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.end()


class PageMotion(QObject):
    """Own at most one snapshot; rapid navigation replaces the previous fade."""
    def __init__(self, target):
        super().__init__(target)
        self.target = target
        self.layer = None
        self.depth = 0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(PAGE_DURATION)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._advance)
        self.animation.finished.connect(self.stop)
        target.installEventFilter(self)
        QApplication.instance().installEventFilter(self)

    def _advance(self, value):
        if self.layer:
            self.layer.opacity = float(value)
            self.layer.update()

    def stop(self):
        self.animation.stop()
        if self.layer:
            self.layer.hide()
            self.layer.deleteLater()
            self.layer = None

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.target and kind in (QEvent.Type.Resize, QEvent.Type.Hide):
            self.stop()
        elif (
            self.layer
            and kind in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel)
            and isinstance(watched, QWidget)
            and (watched is self.target or self.target.isAncestorOf(watched))
        ):
            # Reveal the live destination before a child receives user input.
            self.stop()
        return False

    @contextmanager
    def changing(self):
        outermost = self.depth == 0
        frame = None
        if outermost:
            if self.target.isVisible() and motion_enabled(self.target):
                # Include an interrupted fade to avoid a visual jump on rapid navigation.
                frame = self.target.grab()
            self.stop()
        self.depth += 1
        try:
            yield
        except BaseException:
            if outermost:
                self.stop()
            raise
        else:
            if outermost and frame is not None and not frame.isNull() and motion_enabled(self.target):
                layer = SnapshotLayer(self.target, frame)
                self.layer = layer
                layer.show()
                # Showing an embedded page can synchronously resize its stack.
                # The resize handler deliberately discards an obsolete snapshot.
                if self.layer is layer:
                    layer.raise_()
                    self.animation.setStartValue(1.0)
                    self.animation.setEndValue(0.0)
                    self.animation.start()
        finally:
            self.depth -= 1


def animate_change(method):
    """Animate a shell route only; nested route calls share the outer snapshot."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.motion.changing():
            return method(self, *args, **kwargs)
    return wrapped


class MotionButton(QPushButton):
    """Native button semantics with painted hover and press feedback."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setProperty('animated', True)
        self.hover_amount = 0.0
        self.press_amount = 0.0
        self.hover_animation = self._animation(HOVER_DURATION, self._hover)
        self.press_animation = self._animation(PRESS_DURATION, self._press)
        self.pressed.connect(lambda: self._start(self.press_animation, self.press_amount, 1.0))
        self.released.connect(lambda: self._start(self.press_animation, self.press_amount, 0.0))

    def _animation(self, duration, callback):
        animation = QVariantAnimation(self)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(callback)
        return animation

    def _hover(self, value):
        self.hover_amount = float(value)
        self.update()

    def _press(self, value):
        self.press_amount = float(value)
        self.update()

    def _start(self, animation, current, target):
        animation.stop()
        if not motion_enabled(self):
            if animation is self.hover_animation:
                self._hover(target)
            else:
                self._press(target)
            return
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.start()

    def enterEvent(self, event):
        self._start(self.hover_animation, self.hover_amount, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._start(self.hover_animation, self.hover_amount, 0.0)
        super().leaveEvent(event)

    def settle_motion(self):
        self.hover_animation.stop()
        self.press_animation.stop()
        self._hover(float(self.underMouse()))
        self._press(float(self.isDown()))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self.hover_animation.stop()
            self.press_animation.stop()
            self._hover(0.0)
            self._press(0.0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isEnabled():
            return
        amount = .075 * self.hover_amount + .08 * self.press_amount
        if amount <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(238, 227, 255, round(255 * amount)))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        painter.end()


def apply_motion_preferences(window):
    if motion_enabled(window):
        return
    for controller in window.findChildren(PageMotion):
        controller.stop()
    for widget in window.findChildren(QWidget):
        settle = getattr(widget, 'settle_motion', None)
        if settle:
            settle()
