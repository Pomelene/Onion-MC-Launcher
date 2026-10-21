"""Reusable Qt controls: native text rendering, scalable icons and glass surfaces."""
from PySide6.QtCore import Qt, QSize, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath, QFontDatabase, QFont
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QScrollArea,QSizePolicy,QDialog,QProgressBar,QMessageBox,QLayout)

STYLE = '''
QMainWindow, QDialog { background: #edf3fa; }
QWidget { color:#25354c; font-family:'Microsoft YaHei UI'; font-size:13px; }
QWidget#sidebar { background:rgba(249,252,255,235); border-right:1px solid #e6edf6; }
QFrame#card { background:rgba(255,255,255,215); border:1px solid rgba(255,255,255,160); border-radius:12px; }
QFrame#hero { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #edf5ff,stop:1 #dcecff); border-radius:16px; }
QLabel { background:transparent; }
QLabel#title { font-size:25px; font-weight:600; color:#1c2e46; }
QLabel#heading { font-size:16px; font-weight:600; }
QLabel#muted { color:#78879b; font-size:12px; }
QLabel#eyebrow { color:#6388b4; font-size:11px; font-weight:600; }
QLabel#pill { color:#4774a5; background:#eaf2fc; padding:4px 9px; border-radius:5px; font-size:11px; }
QPushButton { background:transparent; border:0; border-radius:6px; padding:8px 13px; min-height:19px; color:#46617e; }
QPushButton:hover { background:#e8f0fa; }
QPushButton:pressed { background:#dce8f7; }
QPushButton:focus { border:1px solid #76a9e9; }
QPushButton:disabled { color:#9eaabb; background:#e9eef5; }
QPushButton[role='primary'] { background:#2378d8; color:white; font-weight:600; }
QPushButton[role='primary']:hover { background:#3989e4; }
QPushButton[role='primary']:pressed { background:#1c63b5; }
QPushButton[role='soft'] { background:#e6f0fc; color:#2b6aaf; }
QPushButton[role='danger'] { color:#b64b54; }
QPushButton[role='nav'] { text-align:left; padding:11px 18px; border-radius:8px; color:#697b93; }
QPushButton[role='nav']:checked { background:#e0edfd; color:#226bbd; font-weight:600; }
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit,QListWidget,QTreeWidget { background:#fbfdff; border:1px solid #e1e9f3; border-radius:6px; padding:8px 10px; selection-background-color:#d6e8ff; selection-color:#184f8c; }
QLineEdit,QComboBox,QSpinBox { min-height:20px; }
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus { border:1px solid #82afe5; }
QComboBox::drop-down { border:0; width:25px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#e2edfb; color:#25354c; padding:5px; }
QScrollArea { border:0; background:transparent; }
QScrollArea>QWidget>QWidget { background:transparent; }
QScrollBar:vertical { background:transparent; width:7px; margin:0; }
QScrollBar::handle:vertical { background:#c5d3e5; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QProgressBar { border:0; background:#e2ebf6; border-radius:4px; height:7px; text-align:center; }
QProgressBar::chunk { background:#3987de; border-radius:4px; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:10px 18px; color:#7b8ba1; background:transparent; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#2473ca; border-bottom-color:#2473ca; }
QHeaderView::section { background:#f1f6fc; border:0; padding:8px; color:#6c7e96; }
QTreeWidget::item { padding:8px; }
QTreeWidget::item:selected { background:#e4effc; color:#285c9a; }
QCheckBox { spacing:9px; padding:6px 0; min-height:20px; }
QCheckBox::indicator { width:16px; height:16px; }
'''


def configure_fonts(application):
    """Load an installed Windows CJK font, including in the offscreen platform.

    System font files are read in place and are never bundled or redistributed.
    """
    import os
    from pathlib import Path
    directory = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    for filename in ('msyh.ttc', 'msyhbd.ttc'):
        path = directory / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    application.setFont(QFont('Microsoft YaHei UI', 10))

PATHS = {
 'play':[[(8,5),(19,12),(8,19),(8,5)]], 'plus':[[(12,5),(12,19)],[(5,12),(19,12)]],
 'download':[[(12,3),(12,15)],[(7,10),(12,15),(17,10)],[(4,16),(4,21),(20,21),(20,16)]],
 'folder':[[(3,7),(3,20),(21,20),(21,7),(12,7),(10,4),(3,4),(3,7)]],
 'settings':[[(3,6),(21,6)],[(3,12),(21,12)],[(3,18),(21,18)]],
 'search':[[(15,15),(21,21)]], 'account':[[(4,21),(4,18),(7,15),(17,15),(20,18),(20,21)]],
 'package':[[(3,7),(12,3),(21,7),(21,17),(12,21),(3,17),(3,7),(12,11),(21,7)],[(12,11),(12,21)]],
 'home':[[(3,11),(12,3),(21,11)],[(6,9),(6,21),(18,21),(18,9)],[(10,21),(10,15),(14,15),(14,21)]],
 'grid':[[(3,3),(10,3),(10,10),(3,10),(3,3)],[(14,3),(21,3),(21,10),(14,10),(14,3)],[(3,14),(10,14),(10,21),(3,21),(3,14)],[(14,14),(21,14),(21,21),(14,21),(14,14)]],
 'history':[[(3,5),(3,11),(9,11)],[(12,7),(12,12),(16,14)]],
 'world':[[(3,8),(9,8),(11,12),(9,17),(12,21)],[(14,3),(14,8),(20,11)]],
 'arrow':[[(5,12),(19,12)],[(14,7),(19,12),(14,17)]],
 'java':[[(5,9),(5,17),(8,20),(15,20),(18,17),(18,9),(5,9)],[(18,10),(22,10),(22,14),(18,14)],[(10,6),(11,3)]],
}

def icon(name, color='#6c85a5'):
    image=QPixmap(72,72); image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.scale(3,3)
    painter.setPen(QPen(QColor(color),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    if name in ('search','account','world','history'):
        rect={'search':(3,3,14,14),'account':(8,3,8,8),'world':(2,2,20,20),'history':(3,3,18,18)}[name]
        painter.drawEllipse(QRectF(*rect))
    for points in PATHS.get(name,PATHS['package']):
        path=QPainterPath(QPointF(*points[0]))
        for point in points[1:]:path.lineTo(QPointF(*point))
        if name=='play':painter.fillPath(path,QColor(color))
        else:painter.drawPath(path)
    painter.end();image.setDevicePixelRatio(3)
    return QIcon(image)


def label(text,kind='',wrap=False):
    widget=QLabel(text);widget.setTextFormat(Qt.TextFormat.PlainText)
    if kind:widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, role='', glyph=None):
    item=QPushButton(text);item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setProperty('role',role)
    if glyph:item.setIcon(icon(glyph,'#ffffff' if role=='primary' else '#6684a6'));item.setIconSize(QSize(17,17))
    if callback:item.clicked.connect(lambda checked=False: callback())
    return item


def column(parent=None,margin=0,spacing=12):
    layout=QVBoxLayout(parent);layout.setContentsMargins(margin,margin,margin,margin);layout.setSpacing(spacing)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    return layout


def row(parent=None,margin=0,spacing=10):
    layout=QHBoxLayout(parent);layout.setContentsMargins(margin,margin,margin,margin);layout.setSpacing(spacing)
    return layout


class Card(QFrame):
    def __init__(self,title='',subtitle='',parent=None):
        super().__init__(parent);self.setObjectName('card');self.body=column(self,20,12)
        if title:self.body.addWidget(label(title,'heading'))
        if subtitle:self.body.addWidget(label(subtitle,'muted',True))


class Empty(Card):
    def __init__(self,title,description,glyph='package',action='',callback=None):
        super().__init__();self.body.setContentsMargins(28,34,28,34)
        image=QLabel();image.setPixmap(icon(glyph).pixmap(38,38));image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(image)
        for text,kind in ((title,'heading'),(description,'muted')):
            item=label(text,kind,True);item.setAlignment(Qt.AlignmentFlag.AlignCenter);self.body.addWidget(item)
        if action:
            holder=row();holder.addStretch();holder.addWidget(button(action,callback,'soft'));holder.addStretch();self.body.addLayout(holder)


class Page(QScrollArea):
    def __init__(self):
        super().__init__();self.setWidgetResizable(True)
        self.content=QWidget();self.body=column(self.content,0,14);self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.content)


def clear(layout):
    while layout.count():
        item=layout.takeAt(0)
        if item.widget():item.widget().deleteLater()
        elif item.layout():clear(item.layout())


class TaskDialog(QDialog):
    def __init__(self,parent,title):
        super().__init__(parent);self.setWindowTitle(title);self.resize(470,190);self.setModal(True)
        self.body=column(self,24,15);self.message=label('准备中…','heading',True);self.body.addWidget(self.message)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.body.addWidget(self.progress)
        self.cancel_button=button('取消');self.body.addWidget(self.cancel_button,alignment=Qt.AlignmentFlag.AlignRight)
        self.job=None;self.cancel_button.clicked.connect(self.cancel_job)

    def update_progress(self,value):
        if isinstance(value,str):self.message.setText(value)
        elif isinstance(value,tuple) and len(value)==2:
            done,total=value;self.progress.setRange(0,max(1,total));self.progress.setValue(done)

    def cancel_job(self):
        if self.job:self.job.cancel.set()
        self.cancel_button.setEnabled(False);self.message.setText('正在取消，请稍候…')

    def reject(self):
        self.cancel_job()
