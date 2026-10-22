"""Spatial motion on live widgets, with no screen captures or page opacity.

Page content moves 18px, sidebar selection travels between rows, and controls
retain native input behavior. All movements are short and interruptible.
"""
from contextlib import contextmanager
from functools import wraps

from PySide6.QtCore import QObject, QEvent, Qt, QPoint, QRect, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QStyle, QStyleOptionButton, QStylePainter


HOVER_DURATION = 140
PRESS_DURATION = 80


def motion_enabled(widget):
    config = getattr(widget.window(), 'config_obj', None)
    return bool(config.get('ui_animations')) if config else True


class PageMotion(QObject):
    """Slide the real destination by 18px; never capture or fade a page."""
    def __init__(self, target):
        super().__init__(target)
        self.target = target
        self.page = None
        self.origin = QPoint()
        self.depth = 0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(240)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._advance)
        self.animation.finished.connect(self.stop)
        target.installEventFilter(self)
        QApplication.instance().installEventFilter(self)

    @property
    def running(self):
        return self.page is not None

    def _advance(self, value):
        if self.page is not None:
            self.page.move(self.origin + QPoint(round(float(value)), 0))

    def stop(self):
        self.animation.stop()
        if self.page is not None:
            self.page.move(self.origin)
            self.page = None

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.target and kind in (QEvent.Type.Resize, QEvent.Type.Hide):
            self.stop()
        elif (self.running and kind in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel)
              and isinstance(watched, QWidget)
              and (watched is self.target or self.target.isAncestorOf(watched))):
            self.stop()
        return False

    @contextmanager
    def changing(self):
        outermost = self.depth == 0
        if outermost:
            self.stop()
        self.depth += 1
        try:
            yield
        except BaseException:
            if outermost:
                self.stop()
            raise
        else:
            if outermost and self.target.isVisible() and motion_enabled(self.target):
                self.target.layout().activate()
                page = self.target.currentWidget()
                if page is not None:
                    self.page = page
                    self.origin = self.target.contentsRect().topLeft()
                    self.animation.setStartValue(18.0)
                    self.animation.setEndValue(0.0)
                    self.animation.start()
        finally:
            self.depth -= 1


class SelectionRail(QWidget):
    """A persistent sidebar marker travels to the selected row at full opacity."""
    def __init__(self, sidebar):
        super().__init__(sidebar)
        self.item = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.setGeometry)
        sidebar.installEventFilter(self)
        self.hide()

    def select(self, item, animate=True):
        self.animation.stop()
        self.item = item
        if item is None:
            self.hide()
            return
        self.parentWidget().layout().activate()
        point = item.mapTo(self.parentWidget(), QPoint(10, 16))
        destination = QRect(point.x(), point.y(), 3, item.height()-32)
        if animate and self.isVisible() and motion_enabled(self):
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(destination)
            self.animation.start()
        else:
            self.setGeometry(destination)
        self.show()
        self.raise_()

    def settle_motion(self):
        from shiboken6 import isValid
        self.select(self.item if self.item is not None and isValid(self.item) else None, False)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self, self.settle_motion)
        return False

    def paintEvent(self, event):
        config = getattr(self.window(), 'config_obj', None)
        accent = config.get('accent_color') if config else '#cebafa'
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent))
        painter.drawRoundedRect(self.rect(), 1.5, 1.5)
        painter.end()


def animate_change(method):
    """Nested route calls share a single movement of the live page."""
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
        option = QStyleOptionButton()
        self.initStyleOption(option)
        native = QStylePainter(self)
        native.drawControl(QStyle.ControlElement.CE_PushButtonBevel, option)
        # Move only the label/icon while the hit target and layout remain fixed.
        option.state &= ~QStyle.StateFlag.State_Sunken
        native.translate(0, self.press_amount * 1.5)
        native.drawControl(QStyle.ControlElement.CE_PushButtonLabel, option)
        native.end()
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
