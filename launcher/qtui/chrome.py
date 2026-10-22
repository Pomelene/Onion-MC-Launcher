"""Shared dark window chrome with native Qt move/resize operations.

The header stays inside the client area. Launcher dialogs are decorated before
display; file pickers use the platform dialog. Embedded subpages and popups keep
their existing layout and input behavior.
"""
from .choices import ActionMenu
from PySide6.QtCore import QObject, QEvent, Qt, QRect, QTimer
from PySide6.QtGui import QPainter,QFontMetrics
from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget,
    QHBoxLayout, QLabel, QMenu, QSizePolicy, QFileDialog, QColorDialog)
from .widgets import button


class ResizeHandle(QWidget):
    def __init__(self, controller, edges, cursor):
        super().__init__(controller.window)
        self.controller = controller
        self.edges = edges
        self.setObjectName('windowResizeGrip')
        self.setCursor(cursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.start_resize(self.edges)
            event.accept()
        else:
            super().mousePressEvent(event)


class FrameController(QObject):
    def __init__(self, window, maximize=True):
        super().__init__(window)
        self.window = window
        self.allow_maximize = maximize
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        window.installEventFilter(self)
        top, bottom, left, right = Qt.Edge.TopEdge, Qt.Edge.BottomEdge, Qt.Edge.LeftEdge, Qt.Edge.RightEdge
        self.edges = [top, bottom, left, right, top|left, top|right, bottom|left, bottom|right]
        cursors = [Qt.CursorShape.SizeVerCursor]*2 + [Qt.CursorShape.SizeHorCursor]*2 + [
            Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
            Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeFDiagCursor]
        self.handles = [ResizeHandle(self, edge, cursor) for edge, cursor in zip(self.edges, cursors)]

    def start_move(self):
        handle = self.window.windowHandle()
        return bool(handle and handle.startSystemMove())

    def start_resize(self, edges):
        if self.window.isMaximized() or self.window.isFullScreen():
            return False
        handle = self.window.windowHandle()
        return bool(handle and handle.startSystemResize(edges))

    def toggle_maximize(self):
        if not self.allow_maximize:
            return
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    def sync(self):
        window = self.window
        active = window.isWindow() and not window.isMaximized() and not window.isFullScreen()
        size = 5
        width, height = window.width(), window.height()
        rectangles = [QRect(size,0,width-2*size,size), QRect(size,height-size,width-2*size,size),
                      QRect(0,size,size,height-2*size), QRect(width-size,size,size,height-2*size),
                      QRect(0,0,size,size), QRect(width-size,0,size,size),
                      QRect(0,height-size,size,size), QRect(width-size,height-size,size,size)]
        for grip, rectangle in zip(self.handles, rectangles):
            grip.setGeometry(rectangle)
            grip.setVisible(active)
            grip.raise_()
        controls = getattr(window, '_window_controls', None)
        if controls and controls.get('maximize'):
            control = controls['maximize']
            control.setProperty('onionGlyph','restore' if window.isMaximized() else 'maximize')
            control.update()
            text = '还原窗口' if window.isMaximized() else '最大化'
            control.setToolTip(text)
            control.setAccessibleName(text)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange):
            self.sync()
        return False


class TitleBar(QWidget):
    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        self.setObjectName('toolbar')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.start_move()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.toggle_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        window = self.controller.window
        menu = ActionMenu(self)
        if self.controller.allow_maximize:
            menu.addAction('还原', window.showNormal).setEnabled(window.isMaximized())
            menu.addAction('最小化', window.showMinimized)
            menu.addAction('最大化', window.showMaximized).setEnabled(not window.isMaximized())
            menu.addSeparator()
        menu.addAction('关闭', window.reject if isinstance(window,QDialog) else window.close)
        menu.exec(event.globalPos())


def window_controls(controller):
    window = controller.window
    panel = QWidget()
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(0,0,7,0)
    layout.setSpacing(0)
    controls = {}
    actions = [('minimize','最小化',window.showMinimized),
               ('maximize','最大化',controller.toggle_maximize)] if controller.allow_maximize else []
    actions.append(('close','关闭',window.reject if isinstance(window,QDialog) else window.close))
    for glyph, text, callback in actions:
        control = button('',callback,glyph=glyph)
        control.setObjectName('windowClose' if glyph=='close' else 'windowControl')
        control.setFixedSize(42,36)
        control.setToolTip(text)
        control.setAccessibleName(text)
        layout.addWidget(control)
        controls[glyph] = control
    window._window_controls = controls
    return panel


class ChromeMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.frame_controller = FrameController(self)
        self._resize_flush=QTimer(self);self._resize_flush.setSingleShot(True)
        self._resize_flush.timeout.connect(self._finish_resize)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        # Windows layered surfaces need a complete dirty region after shrinking too.
        # Coalesce resize/layout events; never repaint synchronously inside resize.
        if hasattr(self,'_resize_flush'):self._resize_flush.start(0)

    def _finish_resize(self):
        central=self.centralWidget()
        if central is not None:
            if central.layout() is not None:central.layout().activate()
            central.update()
        self.update()


class WindowTitle(QLabel):
    def paintEvent(self,event):
        painter=QPainter(self);painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        text=QFontMetrics(self.font()).elidedText(self.text(),Qt.TextElideMode.ElideRight,self.contentsRect().width())
        painter.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)
        painter.end()


class DialogChromeManager(QObject):
    def sync_header(self,dialog):
        if dialog.minimumWidth()<320:dialog.setMinimumWidth(320)
        header=dialog._chrome_header
        header.setGeometry(0,0,dialog.width(),46)
        header.raise_()
        layout=dialog.layout()
        if layout is not None:
            # Qt's standard dialogs own and sometimes rebuild their layouts.
            # Keep ownership intact and reserve space instead of reparenting it.
            margins=layout.contentsMargins()
            if getattr(dialog,'_chrome_layout',None) is not layout:
                dialog._chrome_layout=layout
                dialog._chrome_margins=(margins.left(),margins.top()+46,margins.right(),margins.bottom())
            desired=dialog._chrome_margins
            if (margins.left(),margins.top(),margins.right(),margins.bottom())!=desired:
                layout.setContentsMargins(*desired)
        dialog.frame_controller.sync()

    def eventFilter(self, dialog, event):
        if not isinstance(dialog,QDialog):
            return False
        # File/folder selection belongs to the OS. Do not change flags, options,
        # layouts or styles: these can prevent Qt from using the native picker.
        if isinstance(dialog,QFileDialog):
            return False
        if event.type() in (QEvent.Type.PolishRequest,QEvent.Type.Show):
            if isinstance(dialog,QColorDialog):dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog,True)
        if event.type() == QEvent.Type.ParentChange and not dialog.isWindow():
            header = getattr(dialog,'_chrome_header',None)
            if header:
                header.hide()
                if getattr(dialog,'_chrome_layout',None) is dialog.layout():
                    left,top,right,bottom=dialog._chrome_margins
                    dialog.layout().setContentsMargins(left,top-46,right,bottom)
                    dialog._chrome_layout=None
                dialog.frame_controller.sync()
        if getattr(dialog,'_chrome_header',None) and dialog.isWindow():
            if event.type() in (QEvent.Type.Show,QEvent.Type.Resize,QEvent.Type.LayoutRequest):
                self.sync_header(dialog)
            return False
        # Polish can run inside a standard dialog's C++ constructor, before its
        # final Python wrapper and layout exist. Wait for the posted request or
        # the first show, still before any client-area paint.
        if event.type() not in (QEvent.Type.PolishRequest,QEvent.Type.Show) or not dialog.isWindow():
            return False
        if dialog.windowType() in (Qt.WindowType.Popup,Qt.WindowType.ToolTip) or getattr(dialog,'_chrome_decorating',False):
            return False
        if dialog.layout() is None:
            return False
        dialog._chrome_decorating=True
        was_visible=dialog.isVisible()
        controller = FrameController(dialog,maximize=False)
        dialog.frame_controller = controller
        header = TitleBar(controller)
        dialog._chrome_header = header
        header.setFixedHeight(46)
        line = QHBoxLayout(header)
        line.setContentsMargins(16,0,0,0)
        title = WindowTitle(dialog.windowTitle())
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName('heading')
        title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        line.addWidget(title,1)
        line.addWidget(window_controls(controller))
        dialog.windowTitleChanged.connect(title.setText)
        dialog.windowTitleChanged.connect(title.setToolTip)
        title.setToolTip(dialog.windowTitle())
        owner = dialog.parentWidget()
        while owner is not None and not owner.styleSheet():
            owner = owner.parentWidget()
        if owner is not None:
            dialog.setStyleSheet(owner.styleSheet())
        else:
            from .widgets import themed_style
            dialog.setStyleSheet(themed_style())
        self.sync_header(dialog)
        header.show()
        dialog._chrome_decorating=False
        if was_visible and not dialog.isVisible():dialog.show()
        return False


def install_window_chrome(application):
    if getattr(application,'_onion_dialog_chrome',None):
        return
    manager = DialogChromeManager(application)
    application.installEventFilter(manager)
    application._onion_dialog_chrome = manager
