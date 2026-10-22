"""Local, interruptible control motion on a stable page and sidebar layout."""
from PySide6.QtCore import QObject, QEvent, Qt, QPoint, QPointF, QRectF, QTimer, QVariantAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QPushButton, QStyle, QStyleOption, QStyleOptionButton, QStylePainter


HOVER_DURATION = 140
PRESS_DURATION = 150


def motion_enabled(widget):
    config = getattr(widget.window(), 'config_obj', None)
    return bool(config.get('ui_animations')) if config else True


class SelectionRail(QObject):
    """One background capsule; its leading edge moves before its trailing edge.

    Rectangles stay in floating point and are painted behind stable buttons.
    Layout measurement never animates; only an actual selection change does.
    """
    EDGE_DURATION = 150
    TRAILING_DELAY = 120

    def __init__(self, sidebar):
        super().__init__(sidebar)
        self.sidebar = sidebar
        self.item = None
        self.rect = QRectF()
        self.destination = QRectF()
        self.initial = QRectF()
        self.visible = False
        self.trailing_top = False
        self.curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
        self.curve.addCubicBezierSegment(QPointF(.4, 0), QPointF(.2, 1), QPointF(1, 1))
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(self.EDGE_DURATION + self.TRAILING_DELAY)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(float(self.animation.duration()))
        self.animation.valueChanged.connect(self._advance)
        self.animation.finished.connect(self._finish)
        self.measure_timer = QTimer(self)
        self.measure_timer.setSingleShot(True)
        self.measure_timer.timeout.connect(self._remeasure)
        sidebar.installEventFilter(self)

    @property
    def running(self):
        return self.animation.state() == QAbstractAnimation.State.Running

    def _target_rect(self):
        from shiboken6 import isValid
        if self.item is None or not isValid(self.item) or self.item.isHidden():
            return QRectF()
        point = self.item.mapTo(self.sidebar, QPoint(10, 3))
        return QRectF(point.x(), point.y(), self.item.width()-20, self.item.height()-6)

    def select(self, item, animate=True):
        self.item = item
        self.sidebar.layout().activate()
        target = self._target_rect()
        if target.isEmpty():
            self.animation.stop()
            self.visible = False
            self.sidebar.update()
            return
        # Repeated clicks or layout notifications cannot restart a live capsule.
        if self.visible and target == self.destination:
            return
        self.animation.stop()
        self.initial = QRectF(self.rect)
        self.destination = target
        if animate and self.visible and self.sidebar.isVisible() and motion_enabled(self.sidebar):
            self.trailing_top = target.top() > self.rect.top()
            self.animation.start()
        else:
            self._finish()
        self.visible = True
        self.sidebar.update()

    def _edge(self, start, end, elapsed, delay=0):
        progress = max(0.0, min(1.0, (elapsed-delay)/self.EDGE_DURATION))
        return start + (end-start)*self.curve.valueForProgress(progress)

    def _advance(self, elapsed):
        top_delay = self.TRAILING_DELAY if self.trailing_top else 0
        bottom_delay = 0 if self.trailing_top else self.TRAILING_DELAY
        left = self._edge(self.initial.left(), self.destination.left(), elapsed)
        right = self._edge(self.initial.right(), self.destination.right(), elapsed)
        top = self._edge(self.initial.top(), self.destination.top(), elapsed, top_delay)
        bottom = self._edge(self.initial.bottom(), self.destination.bottom(), elapsed, bottom_delay)
        self.rect = QRectF(QPointF(left, top), QPointF(right, bottom))
        self.sidebar.update()

    def _finish(self):
        self.rect = QRectF(self.destination)
        self.sidebar.update()

    def _remeasure(self):
        target = self._target_rect()
        if target.isEmpty():
            self.animation.stop()
            self.visible = False
        elif target != self.destination:
            self.animation.stop()
            self.destination = target
            self._finish()
        self.sidebar.update()

    def settle_motion(self):
        self.animation.stop()
        self._remeasure()
        self._finish()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            self.measure_timer.start(0)
        elif event.type() == QEvent.Type.Hide:
            self.animation.stop()
            self._finish()
        return False


class NavigationSurface(QWidget):
    """Paint the capsule below native navigation children, without an overlay."""
    def __init__(self):
        super().__init__()
        self.selection = SelectionRail(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        if self.selection.visible:
            config = getattr(self.window(), 'config_obj', None)
            color = QColor(config.get('accent_color') if config else '#cebafa')
            color.setAlpha(44)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(self.selection.rect, 8, 8)
        painter.end()


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
        native.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Scale the visual button as one unit; its layout and hit area stay fixed.
        scale = 1.0 - .03 * self.press_amount
        center = self.rect().center()
        native.translate(center)
        native.scale(scale, scale)
        native.translate(-center)
        option.state &= ~QStyle.StateFlag.State_Sunken
        native.drawControl(QStyle.ControlElement.CE_PushButtonBevel, option)
        native.drawControl(QStyle.ControlElement.CE_PushButtonLabel, option)
        if self.isEnabled() and self.hover_amount > 0:
            native.setPen(Qt.PenStyle.NoPen)
            native.setBrush(QColor(238, 227, 255, round(255 * .075 * self.hover_amount)))
            native.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        native.end()


def apply_motion_preferences(window):
    if motion_enabled(window):
        return
    for controller in window.findChildren(SelectionRail):
        controller.settle_motion()
    for widget in window.findChildren(QWidget):
        settle = getattr(widget, 'settle_motion', None)
        if settle:
            settle()
