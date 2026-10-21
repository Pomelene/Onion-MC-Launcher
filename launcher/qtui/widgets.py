"""Reusable Qt controls: native text rendering, scalable icons and glass surfaces."""
from PySide6.QtCore import Qt, QSize, QRectF, QPointF, QVariantAnimation, QEasingCurve, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath, QFontDatabase, QFont, QLinearGradient, QRadialGradient, QImageReader, QFontMetrics
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QScrollArea,QSizePolicy,QDialog,QProgressBar,QMessageBox,QLayout,QAbstractButton,QCheckBox,QSpinBox,QComboBox,QLineEdit,QAbstractSpinBox,QStyle,QStyleOptionComboBox)

# Shared flat surfaces and compact list controls, matching the supplied reference.
STYLE = '''
QMainWindow,QDialog { background:#15131a; }
QWidget { color:#e6e1eb; font-family:'Microsoft YaHei UI'; font-size:13px; }
QWidget#sidebar,QWidget#toolbar { background:#19161e; }
QWidget#workspace { background:#15131a; }
QLabel { background:transparent; }
QLabel#title { font-size:23px; font-weight:600; }
QLabel#heading { font-size:15px; font-weight:600; }
QLabel#muted { color:#aaa3b3; font-size:11px; }
QLabel#eyebrow { color:#c3bbcc; font-size:11px; font-weight:400; }
QLabel#settingTitle { color:#e6e1eb; font-size:13px; font-weight:400; }
QLabel#pill { color:#d2c6e4; background:#373040; padding:2px 5px; border-radius:2px; font-size:11px; }
QFrame#card { background:rgba(15,13,19,225); border:0; border-radius:3px; }
QPushButton { background:transparent; border:0; border-radius:2px; padding:7px 10px; min-height:20px; color:#e0d9e7; }
QPushButton:hover { background:rgba(213,199,235,18); }
QPushButton:pressed { background:rgba(213,199,235,28); }
QPushButton:focus { border:0; background:rgba(213,199,235,15); }
QPushButton:disabled { color:#6f6879; background:transparent; }
QPushButton[role='primary'] { background:#c9b8e4; color:#30223e; border-radius:3px; font-weight:500; }
QPushButton[role='primary']:hover { background:#d8c8ef; }
QPushButton[role='soft'] { background:transparent; color:#d6c8e8; }
QPushButton[role='danger'] { color:#ef9baf; }
QPushButton[role='nav'] { text-align:left; border-radius:0; padding:10px 16px; color:#ded7e7; }
QPushButton[role='nav']:checked { background:#302b38; font-weight:600; }
QPushButton[role='tab'] { border-radius:0; border-bottom:2px solid transparent; }
QPushButton[role='tab']:checked { background:transparent; border-bottom:2px solid #c9b8e4; color:#d9c8ef; }
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit,QListWidget,QTreeWidget { background:#29242f; color:#e5dfeb; border:0; border-radius:3px; padding:7px 10px; selection-background-color:#50445f; }
QLineEdit,QComboBox,QSpinBox { min-height:20px; }
QLineEdit:focus,QPlainTextEdit:focus { border-bottom:1px solid #c9b8e4; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView { background:#28232e; color:#e5dfeb; selection-background-color:#453a51; padding:5px; }
QTreeWidget { background:rgba(15,13,19,220); border-radius:0; }
QTreeWidget::item { padding:10px 6px; border-bottom:1px solid #403947; }
QTreeWidget::item:selected { background:#302a39; color:#f0e9f7; }
QHeaderView::section { background:#1a161f; border:0; padding:8px; color:#a69bad; }
QScrollArea { border:0; background:transparent; }
QScrollArea>QWidget>QWidget { background:transparent; }
QScrollBar:vertical { background:transparent; width:6px; margin:0; }
QScrollBar::handle:vertical { background:#665b74; border-radius:2px; min-height:28px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QProgressBar { background:#342c3e; border:0; border-radius:2px; height:5px; }
QProgressBar::chunk { background:#c9b8e4; border-radius:2px; }
QCheckBox { spacing:9px; padding:5px 0; min-height:18px; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid #9c91a8; border-radius:2px; background:transparent; }
QCheckBox::indicator:checked { background:#c9b8e4; border-color:#c9b8e4; }
QCheckBox::indicator:disabled { border-color:#51495c; background:#29232f; }
QToolTip { background:#302936; color:#e9e0f3; border:0; padding:7px; }
QWidget#settingsSection { background:rgba(15,13,19,235); border-radius:3px; }
QWidget#settingRow { background:transparent; border-bottom:1px solid #403947; }
QWidget#settingRow:hover { background:rgba(212,198,230,5); }
QWidget#settingRow QLineEdit,QWidget#settingRow QComboBox,QWidget#settingRow QSpinBox { background:transparent; border:0; border-radius:0; padding:6px 8px; color:#b7adbf; }
QWidget#settingRow QLineEdit:focus,QWidget#settingRow QSpinBox:focus { background:rgba(212,198,230,8); border-bottom:1px solid #c9b8e4; }
QWidget#listRow { background:rgba(15,13,19,230); border-bottom:1px solid #403947; }
QWidget#listRow:hover { background:rgba(212,198,230,7); }
'''

# Glass is composited inside the launcher; the desktop is never captured.
STYLE += '''
QMainWindow,QDialog { background:#101522; }
QWidget#workspace { background:transparent; }
QWidget#sidebar { background:rgba(18,24,40,155); border-right:1px solid rgba(208,225,255,22); }
QWidget#toolbar { background:rgba(19,25,43,155); border-bottom:1px solid rgba(208,225,255,22); }
QFrame#card { background:rgba(29,37,57,160); border:1px solid rgba(208,225,255,24); border-radius:12px; }
QWidget#settingsSection { background:rgba(23,30,48,185); border:1px solid rgba(208,225,255,24); border-radius:10px; }
QWidget#settingRow { border-bottom:1px solid rgba(208,225,255,22); }
QWidget#settingRow:hover { background:rgba(194,219,255,8); }
QWidget#settingRow QLineEdit,QWidget#settingRow QComboBox,QWidget#settingRow QSpinBox { color:#c8cfe0; }
QLabel#muted { color:#aebbd0; }
QLabel#eyebrow { color:#b6c7dd; }
QPushButton { border-radius:7px; }
QPushButton:hover { background:rgba(193,215,255,20); }
QPushButton:focus { border:1px solid rgba(183,218,255,130); }
QPushButton[role='primary'] { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #b8e8ee,stop:0.52 #bec9f1,stop:1 #d6bde9); color:#182238; border:1px solid rgba(240,248,255,120); border-radius:9px; }
QPushButton[role='primary']:hover { background:#d1e8ff; }
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit,QListWidget { background:rgba(143,169,213,17); border-radius:6px; }
QTreeWidget { background:rgba(19,26,43,165); border-radius:9px; }
QTreeWidget::item { border-bottom:1px solid rgba(208,225,255,24); }
QTreeWidget::item:selected { background:rgba(146,176,234,32); }
QHeaderView::section { background:#202b40; color:#b6c7dd; }
QComboBox QAbstractItemView,QMenu { background:#202b40; color:#e5edfa; border:1px solid #43536f; }
QMenu::item { padding:8px 20px; }
QMenu::item:selected { background:#374965; }
QSpinBox QLineEdit,QWidget#settingRow QSpinBox QLineEdit { padding:0; min-height:0; border:0; background:transparent; }
'''


class GlassBackdrop(QWidget):
    """Soft spectral light, painted at native resolution without a blur loop."""
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#101522'))
        for x,y,r,color in ((.12,.1,.7,'#305e78'),(.78,.2,.65,'#4f3e77'),(.9,.94,.6,'#245b66')):
            g=QRadialGradient(QPointF(self.width()*x,self.height()*y),max(self.width(),self.height())*r)
            c=QColor(color);c.setAlpha(145);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c)
            p.fillRect(self.rect(),g)
        p.end()


def themed_style(accent='#b8e8ee'):
    import re
    if not isinstance(accent,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',accent):accent='#b8e8ee'
    return STYLE+'''
QWidget#settingRow QLineEdit,QWidget#settingRow QSpinBox,QWidget#settingRow QComboBox,QWidget#settingRow QPushButton { color:ACCENT; }
QWidget#settingRow QPushButton { text-align:right; }
QWidget#settingRow QPushButton:hover { background:rgba(193,215,255,20); }
QWidget#settingRow QLineEdit:disabled,QWidget#settingRow QSpinBox:disabled,QWidget#settingRow QComboBox:disabled,QWidget#settingRow QPushButton:disabled { color:#748095; }
QWidget#settingRow QLineEdit:read-only { color:#aebbd0; }
'''.replace('ACCENT',accent)


class SettingsComboBox(QComboBox):
    """Right-align the closed value; retain native popup and keyboard behavior."""
    def paintEvent(self,event):
        option=QStyleOptionComboBox();self.initStyleOption(option);p=QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox,option,p,self)
        rect=self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,self).adjusted(4,0,-4,0)
        p.setPen(option.palette.color(self.foregroundRole()));p.setFont(self.font())
        p.drawText(rect,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,QFontMetrics(self.font()).elidedText(self.currentText(),Qt.TextElideMode.ElideRight,max(0,rect.width())))
        p.end()


class NavigationItem(QAbstractButton):
    """One geometry for icon, title and optional subtitle across the sidebar."""
    def __init__(self,title,glyph,callback,subtitle='',parent=None):
        super().__init__(parent);self.glyph=glyph;self.subtitle=subtitle
        self.setText(title);self.setCursor(Qt.CursorShape.PointingHandCursor);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setCheckable(True);self.clicked.connect(lambda checked=False:callback());self.setSubtitle(subtitle)
        self.hover_amount=0.0;self.hover_animation=QVariantAnimation(self)
        self.hover_animation.setDuration(450);self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self._hover_changed)

    def _hover_changed(self,value):self.hover_amount=float(value);self.update()

    def enterEvent(self,event):
        self.hover_animation.stop();self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(1.0);self.hover_animation.start();super().enterEvent(event)

    def leaveEvent(self,event):
        self.hover_animation.stop();self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(0.0);self.hover_animation.start();super().leaveEvent(event)

    def setSubtitle(self,text):
        self.subtitle=str(text or '');self.setFixedHeight(62 if self.subtitle else 44)
        self.setToolTip(self.text()+(' · '+self.subtitle if self.subtitle else ''));self.update()

    def text_left(self):return 48

    def sizeHint(self):return QSize(220,62 if self.subtitle else 44)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked():
            glow=QLinearGradient(0,0,self.width(),self.height());glow.setColorAt(0,QColor(150,220,245,38));glow.setColorAt(1,QColor(209,177,255,18))
            painter.fillRect(self.rect(),glow);painter.fillRect(0,10,3,self.height()-20,QColor('#b8e8ee'))
        elif self.hover_amount or self.hasFocus():painter.fillRect(self.rect(),QColor(194,220,255,int(18*max(self.hover_amount,float(self.hasFocus())))))
        color='#e3d5f1' if self.isChecked() else '#d0c7d9'
        if not self.isEnabled():color='#726879'
        icon(self.glyph,color).paint(painter,16,(self.height()-20)//2,20,20)
        font=self.font();font.setPixelSize(13);font.setBold(self.isChecked());painter.setFont(font);painter.setPen(QColor(color))
        metrics=QFontMetrics(font);width=max(0,self.width()-self.text_left()-16)
        title=metrics.elidedText(self.text(),Qt.TextElideMode.ElideRight,width)
        painter.drawText(QRectF(self.text_left(),12 if self.subtitle else 0,width,22 if self.subtitle else self.height()),Qt.AlignmentFlag.AlignVCenter,title)
        if self.subtitle:
            font.setPixelSize(11);font.setBold(False);painter.setFont(font);painter.setPen(QColor('#aaa0b6'))
            subtitle=QFontMetrics(font).elidedText(self.subtitle,Qt.TextElideMode.ElideRight,width)
            painter.drawText(QRectF(self.text_left(),33,width,18),Qt.AlignmentFlag.AlignVCenter,subtitle)
        painter.end()


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
 'back':[[(5,12),(19,12)],[(10,7),(5,12),(10,17)]],
 'trash':[[(4,6),(20,6)],[(9,6),(9,3),(15,3),(15,6)],[(6,6),(7,21),(17,21),(18,6)],[(10,10),(10,17)],[(14,10),(14,17)]],
 'up':[[(6,15),(12,9),(18,15)]],
 'java':[[(5,9),(5,17),(8,20),(15,20),(18,17),(18,9),(5,9)],[(18,10),(22,10),(22,14),(18,14)],[(10,6),(11,3)]],
}

def icon(name, color='#c9bfd4'):
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
    if glyph:item.setIcon(icon(glyph,'#352641' if role=='primary' else '#c9bfd4'));item.setIconSize(QSize(18,18))
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


class SettingsSection(QWidget):
    def __init__(self,title='',subtitle='',parent=None):
        super().__init__(parent);outer=column(self,0,0)
        if title:
            heading=label(title,'eyebrow');heading.setContentsMargins(0,12,0,9);outer.addWidget(heading)
        surface=QWidget();surface.setObjectName('settingsSection');self.body=column(surface,0,0);outer.addWidget(surface)
        if subtitle:self.setToolTip(subtitle)


class ToggleSwitch(QCheckBox):
    def __init__(self):
        super().__init__();self.setFixedSize(42,26);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#635371' if self.isChecked() else '#3c3544'));painter.drawRoundedRect(QRectF(4,6,34,14),7,7)
        painter.setBrush(QColor('#cbb7e6' if self.isChecked() else '#93879f') if self.isEnabled() else QColor('#51495c'))
        painter.drawEllipse(QRectF(21 if self.isChecked() else 2,3,20,20));painter.end()


class InlineSpinBox(QSpinBox):
    """Keep the editor usable with borderless, button-free Qt styles."""
    def paintEvent(self,event):
        self.lineEdit().setGeometry(8,4,max(1,self.width()-16),max(1,self.height()-8))
        super().paintEvent(event)


class ContentText(QWidget):
    def __init__(self,title,detail):
        super().__init__();self.title=str(title);self.detail=' '.join(str(detail).split());self.setMinimumWidth(80)
        self.setToolTip(self.title+'\n'+self.detail);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)

    def paintEvent(self,event):
        p=QPainter(self);font=self.font();font.setPixelSize(14);p.setFont(font);p.setPen(QColor('#e5edfa'))
        p.drawText(QRectF(0,4,self.width(),23),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.title,Qt.TextElideMode.ElideRight,self.width()))
        font.setPixelSize(11);p.setFont(font);p.setPen(QColor('#aebbd0'))
        p.drawText(QRectF(0,28,self.width(),18),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.detail,Qt.TextElideMode.ElideRight,self.width()));p.end()


class ContentCheck(QCheckBox):
    def __init__(self):
        super().__init__();self.setFixedSize(24,28);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#b8c7de' if self.isEnabled() else '#687587'),1.5));p.setBrush(QColor('#c9b8e4') if self.isChecked() else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(3,5,18,18),3,3)
        if self.isChecked():
            p.setPen(QPen(QColor('#253047'),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath(QPointF(7,14));path.lineTo(11,18);path.lineTo(18,10);p.drawPath(path)
        if self.hasFocus():p.setPen(QPen(QColor('#b8e8ee'),1,Qt.PenStyle.DotLine));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(self.rect().adjusted(0,0,-1,-1))
        p.end()


class ContentRow(QWidget):
    def __init__(self,title,detail,glyph='package',enabled=None,on_toggle=None):
        super().__init__();self.setObjectName('listRow');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True);self.setFixedHeight(64);self.line=row(self,8,12)
        self.check=None
        if enabled is not None:
            self.check=ContentCheck();self.check.setChecked(enabled);self.check.setToolTip('启用此模组');self.check.setAccessibleName('启用 '+title)
            if on_toggle:self.check.clicked.connect(lambda _:on_toggle())
            self.line.addWidget(self.check)
        self.image=QLabel();self.image.setPixmap(icon(glyph).pixmap(32,32));self.image.setFixedSize(36,36);self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.line.addWidget(self.image)
        self.text=ContentText(title,detail);self.line.addWidget(self.text,1)

    def set_artwork(self,data):
        if not data:return
        buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader=QImageReader(buffer);reader.setDecideFormatFromContent(True);size=reader.size()
        if not size.isValid() or size.width()*size.height()>4_000_000:return
        reader.setScaledSize(size.scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio));image=reader.read()
        if not image.isNull():
            pixmap=QPixmap.fromImage(image);pixmap.setDevicePixelRatio(2);self.image.setPixmap(pixmap)

    def action(self,title,callback,glyph,role=''):
        control=button('',callback,role,glyph);control.setStyleSheet('padding:0;');control.setToolTip(title);control.setAccessibleName(title);control.setFixedSize(34,34);self.line.addWidget(control)


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


class Landscape(QWidget):
    """Resolution-independent, original block landscape for the launch page."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumHeight(235)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),16,16);p.setClipPath(clip)
        scale=max(self.width()/800,self.height()/330)
        p.translate((self.width()-800*scale)/2,(self.height()-330*scale)/2);p.scale(scale,scale)
        gradient=QLinearGradient(0,0,800,330);gradient.setColorAt(0,QColor('#c6e3d8'));gradient.setColorAt(1,QColor('#e8ede0'))
        p.fillRect(QRectF(0,0,800,330),gradient);p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#f6f7dc'));p.drawEllipse(QRectF(590,32,68,68))
        for color,points in [('#a5c5b5',[(0,185),(110,185),(110,150),(220,150),(220,120),(345,120),(345,155),(430,155),(430,182),(800,182),(800,330),(0,330)]),('#739f88',[(0,245),(90,245),(90,212),(188,212),(188,190),(290,190),(290,222),(480,222),(480,198),(610,198),(610,238),(800,238),(800,330),(0,330)]),('#4c7e63',[(0,285),(230,285),(230,260),(390,260),(390,280),(560,280),(560,250),(800,250),(800,330),(0,330)])]:
            path=QPainterPath(QPointF(*points[0]))
            for point in points[1:]:path.lineTo(QPointF(*point))
            path.closeSubpath();p.fillPath(path,QColor(color))
        for x,y,s in [(490,190,1),(700,218,1.2),(80,244,.85)]:
            p.fillRect(QRectF(x+19*s,y-7*s,12*s,60*s),QColor('#5d7861'))
            p.fillRect(QRectF(x,y-42*s,50*s,43*s),QColor('#56856b'))
            p.fillRect(QRectF(x+7*s,y-58*s,36*s,27*s),QColor('#649679'))
        p.end()


class HomeCanvas(Landscape):
    """Local wallpaper rendered at window resolution, with a scalable fallback."""
    def __init__(self,path='',parent=None):
        super().__init__(parent);self.image=None
        if path:
            reader=QImageReader(str(path));size=reader.size()
            if size.isValid() and size.width()*size.height()<=64_000_000:
                reader.setScaledSize(size.scaled(3840,2160,Qt.AspectRatioMode.KeepAspectRatio))
                value=reader.read()
                if not value.isNull():self.image=value

    def paintEvent(self,event):
        if self.image is None:
            GlassBackdrop.paintEvent(self,event)
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(self.width()/1000,self.height()/700)
            for offset,alpha in ((0,36),(18,18),(42,10)):
                path=QPainterPath(QPointF(-100,480+offset));path.cubicTo(220,80+offset,600,650+offset,1110,120+offset)
                gradient=QLinearGradient(0,0,1000,700)
                gradient.setColorAt(0,QColor(122,238,239,alpha));gradient.setColorAt(.52,QColor(203,184,255,alpha));gradient.setColorAt(1,QColor(250,176,220,alpha))
                p.setPen(QPen(gradient,80 if offset==0 else 1.2));p.drawPath(path)
            p.end()
        else:
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            p.drawImage(QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height()),self.image);p.end()
        p=QPainter(self);shade=QLinearGradient(0,self.height()*.55,0,self.height());shade.setColorAt(0,QColor(0,0,0,0));shade.setColorAt(1,QColor(13,31,25,115));p.fillRect(self.rect(),shade);p.end()


def setting_row(layout,title,description,control):
    """A HMCL-style title, explanation and aligned editor row."""
    container=QWidget();container.setObjectName('settingRow');container.setMinimumHeight(50);container.setToolTip(description)
    line=row(container,16,20);line.setContentsMargins(16,6,16,6)
    text=label(title,'settingTitle');text.setToolTip(description);line.addWidget(text,1)
    if isinstance(control,QWidget):
        if isinstance(control,QSpinBox):
            control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);control.setAlignment(Qt.AlignmentFlag.AlignRight);control.setFixedWidth(140)
        elif isinstance(control,QComboBox):control.setFixedWidth(240)
        elif isinstance(control,QLineEdit):control.setMinimumWidth(200);control.setMaximumWidth(650);control.setAlignment(Qt.AlignmentFlag.AlignRight)
        line.addWidget(control)
    else:line.addLayout(control)
    layout.addWidget(container)


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
        if isinstance(value,str):self.message.setText(value);self.progress.setRange(0,0)
        elif isinstance(value,tuple) and len(value)==2:
            done,total=value;self.progress.setRange(0,max(1,total));self.progress.setValue(done)

    def cancel_job(self):
        if self.job:self.job.cancel.set()
        self.cancel_button.setEnabled(False);self.message.setText('正在取消，请稍候…')

    def reject(self):
        self.cancel_job()
