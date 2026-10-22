"""Reusable Qt controls: native text rendering, scalable icons and glass surfaces."""
from PySide6.QtCore import Qt, QSize, QRectF, QPointF, QVariantAnimation, QEasingCurve, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath, QFontDatabase, QFont, QLinearGradient, QRadialGradient, QImageReader, QFontMetrics, QBrush
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QScrollArea,QSizePolicy,QDialog,QProgressBar,QMessageBox,QLayout,QAbstractButton,QCheckBox,QSpinBox,QComboBox,QLineEdit,QAbstractSpinBox,QStyle,QStyleOptionComboBox)

from .theme import STYLE,appearance_style,appearance_values,config_for,paint_color
from .motion import MotionButton,motion_enabled


class GlassBackdrop(QWidget):
    """Soft spectral light, painted at native resolution without a blur loop."""
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),paint_color(self,'base'))
        light=appearance_values(config_for(self))['color_mode']=='light'
        for x,y,r,color in ((.8,.05,.6,'#cab5e8' if light else '#493459'),(.98,.94,.5,'#e3d7f2' if light else '#302c43')):
            g=QRadialGradient(QPointF(self.width()*x,self.height()*y),max(self.width(),self.height())*r)
            c=QColor(color);c.setAlpha(55);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c)
            p.fillRect(self.rect(),g)
        p.end()


def themed_style(accent='#cebafa',config=None):
    import re
    if not isinstance(accent,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',accent):accent='#cebafa'
    return appearance_style(accent,config)


def control_accent(widget):
    """Use the saved accent for painted controls as well as stylesheet controls."""
    import re
    config=config_for(widget)
    value=config.get('accent_color') if config else None
    return value if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) else '#cebafa'


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
        self.hover_animation.setDuration(150);self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self._hover_changed)

    def _hover_changed(self,value):self.hover_amount=float(value);self.update()

    def nextCheckState(self):
        # Navigation owns selection; action rows must not select themselves.
        pass

    def settle_motion(self):
        self.hover_animation.stop();self._hover_changed(float(self.underMouse()))

    def enterEvent(self,event):
        if not motion_enabled(self):self.settle_motion();return super().enterEvent(event)
        self.hover_animation.stop();self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(1.0);self.hover_animation.start();super().enterEvent(event)

    def leaveEvent(self,event):
        if not motion_enabled(self):self.hover_animation.stop();self._hover_changed(0.0);return super().leaveEvent(event)
        self.hover_animation.stop();self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(0.0);self.hover_animation.start();super().leaveEvent(event)

    def setSubtitle(self,text):
        subtitle=str(text or '')
        if self.subtitle==subtitle and self.height()==(68 if subtitle else 48):return
        self.subtitle=subtitle;self.setFixedHeight(68 if self.subtitle else 48)
        self.setToolTip(self.text()+(' · '+self.subtitle if self.subtitle else ''));self.update()

    def text_left(self):return 54

    def sizeHint(self):return QSize(220,68 if self.subtitle else 48)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds=QRectF(self.rect()).adjusted(10,3,-10,-3)
        if not self.isChecked() and (self.hover_amount or self.hasFocus()):
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(194,220,225,int(20*max(self.hover_amount,float(self.hasFocus())))));painter.drawRoundedRect(bounds,7,7)
        role='disabled' if not self.isEnabled() else 'selected_text' if self.isChecked() else 'icon'
        color=paint_color(self,role,text=True)
        icon(self.glyph,paint_color(self,role)).paint(painter,22,(self.height()-20)//2,20,20)
        font=self.font();font.setPixelSize(14);font.setBold(self.isChecked());painter.setFont(font);painter.setPen(QColor(color))
        metrics=QFontMetrics(font);width=max(0,self.width()-self.text_left()-16)
        title=metrics.elidedText(self.text(),Qt.TextElideMode.ElideRight,width)
        painter.drawText(QRectF(self.text_left(),14 if self.subtitle else 0,width,22 if self.subtitle else self.height()),Qt.AlignmentFlag.AlignVCenter,title)
        if self.subtitle:
            font.setPixelSize(12);font.setBold(False);painter.setFont(font);painter.setPen(paint_color(self,'muted',text=True))
            subtitle=QFontMetrics(font).elidedText(self.subtitle,Qt.TextElideMode.ElideRight,width)
            painter.drawText(QRectF(self.text_left(),37,width,18),Qt.AlignmentFlag.AlignVCenter,subtitle)
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
 'minimize':[[(5,12),(19,12)]], 'maximize':[[(5,5),(19,5),(19,19),(5,19),(5,5)]],
 'restore':[[(8,5),(19,5),(19,16)],[(5,8),(16,8),(16,19),(5,19),(5,8)]],
 'close':[[(6,6),(18,18)],[(18,6),(6,18)]],
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

def icon(name, color='#bac7cd'):
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
    item=MotionButton(text);item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setProperty('role',role)
    if glyph:item.setProperty('onionGlyph',glyph);item.setIcon(icon(glyph,'#281f35' if role=='primary' else '#bac7cd'));item.setIconSize(QSize(18,18))
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
    """A fixed hit target; thumb translation, size and colors animate locally."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(42,26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position=0.0
        self.emphasis=0.0
        self.motion=self._animation(self._move)
        self.thumb_motion=self._animation(self._resize_thumb)
        self.toggled.connect(self._animate)
        self.pressed.connect(lambda:self._emphasize(-1.0))
        self.released.connect(lambda:self._emphasize(float(self.underMouse())))

    def _animation(self,callback):
        animation=QVariantAnimation(self)
        animation.setDuration(200)
        curve=QEasingCurve(QEasingCurve.Type.BezierSpline)
        curve.addCubicBezierSegment(QPointF(.4,0),QPointF(.2,1),QPointF(1,1))
        animation.setEasingCurve(curve)
        animation.valueChanged.connect(callback)
        return animation

    def _move(self,value):self.position=float(value);self.update()
    def _resize_thumb(self,value):self.emphasis=float(value);self.update()

    def settle_motion(self):
        self.motion.stop();self.thumb_motion.stop()
        self._move(float(self.isChecked()))
        self._resize_thumb(float(self.underMouse()) if self.isEnabled() else 0.0)

    def _animate(self,checked):
        self.motion.stop()
        if not self.isVisible() or not motion_enabled(self):self._move(float(checked));return
        self.motion.setStartValue(self.position);self.motion.setEndValue(float(checked));self.motion.start()

    def _emphasize(self,target):
        self.thumb_motion.stop()
        if not self.isEnabled():target=0.0
        if not self.isVisible() or not motion_enabled(self):self._resize_thumb(target);return
        self.thumb_motion.setStartValue(self.emphasis);self.thumb_motion.setEndValue(target);self.thumb_motion.start()

    def enterEvent(self,event):self._emphasize(1.0);super().enterEvent(event)
    def leaveEvent(self,event):self._emphasize(0.0);super().leaveEvent(event)
    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(Qt.PenStyle.NoPen)
        accent=QColor(control_accent(self))
        def blend(start,end):
            return QColor.fromRgbF(*[a+(b-a)*self.position for a,b in zip(start.getRgbF(),end.getRgbF())])
        track=blend(paint_color(self,'track'),accent.darker(180))
        thumb=blend(paint_color(self,'thumb'),accent) if self.isEnabled() else paint_color(self,'disabled')
        painter.setBrush(track);painter.drawRoundedRect(QRectF(2,3,38,20),10,10)
        radius=7+self.emphasis
        painter.setBrush(thumb);painter.drawEllipse(QPointF(12+18*self.position,13),radius,radius)
        if self.hasFocus():
            painter.setPen(QPen(accent,1));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(QRectF(0,1,41,24),12,12)
        painter.end()


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
        p=QPainter(self);font=self.font();font.setPixelSize(14);p.setFont(font);p.setPen(paint_color(self,'text',text=True))
        p.drawText(QRectF(0,4,self.width(),23),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.title,Qt.TextElideMode.ElideRight,self.width()))
        font.setPixelSize(12);p.setFont(font);p.setPen(paint_color(self,'muted',text=True))
        p.drawText(QRectF(0,28,self.width(),18),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.detail,Qt.TextElideMode.ElideRight,self.width()));p.end()


class ContentCheck(QCheckBox):
    def __init__(self):
        super().__init__();self.setFixedSize(24,28);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(paint_color(self,'icon' if self.isEnabled() else 'disabled'),1.5));p.setBrush(QColor(control_accent(self)) if self.isChecked() else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(3,5,18,18),3,3)
        if self.isChecked():
            p.setPen(QPen(QColor('#253047'),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath(QPointF(7,14));path.lineTo(11,18);path.lineTo(18,10);p.drawPath(path)
        if self.hasFocus():p.setPen(QPen(QColor(control_accent(self)),1,Qt.PenStyle.DotLine));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(self.rect().adjusted(0,0,-1,-1))
        p.end()


class ContentRow(QWidget):
    def __init__(self,title,detail,glyph='package',enabled=None,on_toggle=None):
        super().__init__();self.glyph=glyph;self.has_artwork=False;self._fallback_color=None;self.setObjectName('listRow');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True);self.setFixedHeight(68);self.line=row(self,10,14)
        self.check=None
        if enabled is not None:
            self.check=ContentCheck();self.check.setChecked(enabled);self.check.setToolTip('启用此模组');self.check.setAccessibleName('启用 '+title)
            if on_toggle:self.check.clicked.connect(lambda _:on_toggle())
            self.line.addWidget(self.check)
        self.image=QLabel();self.image.setPixmap(icon(glyph).pixmap(32,32));self.image.setFixedSize(36,36);self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.line.addWidget(self.image)
        self.text=ContentText(title,detail);self.line.addWidget(self.text,1)

    def paintEvent(self,event):
        if not self.has_artwork:
            color=paint_color(self,'icon')
            if self._fallback_color!=color.rgba():
                self._fallback_color=color.rgba();self.image.setPixmap(icon(self.glyph,color).pixmap(32,32))
        super().paintEvent(event)

    def set_artwork(self,data):
        if not data:return
        buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader=QImageReader(buffer);reader.setDecideFormatFromContent(True);size=reader.size()
        if not size.isValid() or size.width()*size.height()>4_000_000:return
        reader.setScaledSize(size.scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio));image=reader.read()
        if not image.isNull():
            pixmap=QPixmap.fromImage(image);pixmap.setDevicePixelRatio(2);self.image.setPixmap(pixmap);self.has_artwork=True

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


def background_rect(image_size,viewport,mode):
    """Centered image destination in logical pixels; fill crops, fit letterboxes."""
    if mode=='stretch':return QRectF(0,0,viewport.width(),viewport.height())
    if mode=='center':width,height=image_size.width(),image_size.height()
    else:
        ratio=(min if mode=='fit' else max)(viewport.width()/max(1,image_size.width()),viewport.height()/max(1,image_size.height()))
        width,height=image_size.width()*ratio,image_size.height()*ratio
    return QRectF((viewport.width()-width)/2,(viewport.height()-height)/2,width,height)


class HomeCanvas(Landscape):
    """Local wallpaper rendered at window resolution, with a scalable fallback."""
    def __init__(self,path='',parent=None,config=None):
        super().__init__(parent);self.image=None;self.path=None;self.tile=None;self.config_obj=config
        self.set_background(path)

    def set_background(self,path):
        path=str(path or '')
        if self.path==path:return
        self.path=path;self.image=None;self.tile=None
        if path:
            reader=QImageReader(str(path));size=reader.size()
            if size.isValid() and size.width()*size.height()<=64_000_000:
                if size.width()>3840 or size.height()>2160:reader.setScaledSize(size.scaled(3840,2160,Qt.AspectRatioMode.KeepAspectRatio))
                value=reader.read()
                if not value.isNull():self.image=value;self.tile=QPixmap.fromImage(value)
        self.update()

    def paintEvent(self,event):
        values=appearance_values(config_for(self));opacity=1-values['background_transparency']/100
        GlassBackdrop.paintEvent(self,event)
        if self.image is None:
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setOpacity(opacity)
            p.scale(self.width()/1000,self.height()/700)
            for offset,alpha in ((0,36),(18,18),(42,10)):
                path=QPainterPath(QPointF(-100,480+offset));path.cubicTo(220,80+offset,600,650+offset,1110,120+offset)
                gradient=QLinearGradient(0,0,1000,700)
                gradient.setColorAt(0,QColor(168,139,228,alpha));gradient.setColorAt(.52,QColor(203,184,255,alpha));gradient.setColorAt(1,QColor(207,163,224,alpha))
                p.setPen(QPen(gradient,80 if offset==0 else 1.2));p.drawPath(path)
            p.end()
        else:
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(opacity);mode=config_for(self).get('background_mode','fill')
            if mode=='tile':p.fillRect(self.rect(),QBrush(self.tile))
            else:p.drawImage(background_rect(self.image.size(),self.size(),mode),self.image)
            p.end()
        p=QPainter(self);p.setOpacity(opacity);shade=QLinearGradient(0,0,0,self.height())
        light=values['color_mode']=='light'
        shade.setColorAt(0,QColor(250,250,255,90) if light else QColor(10,12,20,20))
        shade.setColorAt(1,QColor(246,246,253,190) if light else QColor(13,20,31,140))
        p.fillRect(self.rect(),shade);p.end()


def setting_row(layout,title,description,control):
    """A HMCL-style title, explanation and aligned editor row."""
    container=QWidget();container.setObjectName('settingRow');container.setMinimumHeight(58);container.setToolTip(description)
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
        if item.widget():
            # Deferred deletion must not leave obsolete rows painting for a frame.
            item.widget().hide()
            item.widget().deleteLater()
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
