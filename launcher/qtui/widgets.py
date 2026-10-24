"""Reusable Qt controls: native text rendering, scalable icons and glass surfaces."""
import time
from collections import deque
from PySide6.QtCore import QTimer, Qt, QSize, QRect, QRectF, QPoint, QPointF, QEvent, QVariantAnimation, QEasingCurve, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPainterPath, QFontDatabase, QFont, QLinearGradient, QRadialGradient, QImageReader, QFontMetrics, QBrush, QImage
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QScrollArea,QSizePolicy,QDialog,QProgressBar,QMessageBox,QLayout,QAbstractButton,QCheckBox,QSpinBox,QComboBox,QLineEdit,QAbstractSpinBox,QStyle,QStyleOptionComboBox)

from .theme import STYLE,appearance_style,appearance_values,config_for,paint_color,surface_opacity,effective_accent,corner,text_size,row_height,preference
from .motion import MotionButton,motion_enabled
from .choices import ChoiceComboBox


def paint_glass_background(p,viewport,widget):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect=QRectF(0,0,viewport.width(),viewport.height())
    p.fillRect(rect,paint_color(widget,'base'))
    light=appearance_values(config_for(widget))['color_mode']=='light'
    for x,y,r,color in ((.8,.05,.6,'#cab5e8' if light else '#493459'),(.98,.94,.5,'#e3d7f2' if light else '#302c43')):
        g=QRadialGradient(QPointF(viewport.width()*x,viewport.height()*y),max(viewport.width(),viewport.height())*r)
        c=paint_color(widget,'container');c.setAlpha(55);g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c)
        p.fillRect(rect,g)


def paint_cached_surface(widget,p,viewport,key,draw,*,layer="background",opacity=None):
    """Cache each painted layer and apply its own opacity exactly once."""
    ratio=widget.devicePixelRatioF();key=(viewport.width(),viewport.height(),ratio,*key)
    key_attribute=f'_{layer}_key';image_attribute=f'_{layer}_image'
    if getattr(widget,key_attribute,None)!=key:
        required=QSize(max(1,round(viewport.width()*ratio)),max(1,round(viewport.height()*ratio)))
        image=getattr(widget,image_attribute,None)
        if image is None or image.devicePixelRatio()!=ratio or image.width()<required.width() or image.height()<required.height():
            image=QImage(required,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(ratio)
        image.fill(0)
        buffer=QPainter(image);draw(buffer,viewport);buffer.end()
        setattr(widget,key_attribute,key);setattr(widget,image_attribute,image)
    p.save();p.setOpacity(surface_opacity(config_for(widget)) if opacity is None else opacity)
    p.drawImage(QPointF(0,0),getattr(widget,image_attribute));p.restore()


class GlassBackdrop(QWidget):
    """Draw an optional single wallpaper beneath the entire window."""
    def paintEvent(self,event):
        p=QPainter(self);owner=self.window();canvas=getattr(owner,'home_canvas',None)
        config=config_for(self);values=appearance_values(config)
        shared=preference(config,'background_scope')=='window'
        home=not shared and canvas is not None and owner.stack.currentWidget() is owner.page_map['home']
        area=QRect(canvas.mapTo(self,QPoint(0,0)),canvas.size()) if home else QRect()
        key=(values['color_mode'],effective_accent(config),shared,home,area.x(),area.y(),area.width(),area.height(),
             values['background_transparency'] if canvas is None or canvas.image is None else 0,preference(config,'background_mode'),canvas.image.cacheKey() if canvas is not None and canvas.image is not None else 0)
        def draw(painter,viewport):
            if shared and canvas is not None:canvas._paint_ui_background(painter,viewport)
            else:
                paint_glass_background(painter,viewport,self)
                if home:
                    painter.save();painter.setClipRect(area);painter.translate(area.topLeft())
                    canvas._paint_ui_background(painter,area.size());painter.restore()
        paint_cached_surface(self,p,self.size(),key,draw)
        if canvas is not None and canvas.image is not None and (shared or home):
            def draw_wallpaper(painter,viewport):
                if shared:canvas._paint_wallpaper(painter,viewport)
                else:
                    painter.save();painter.setClipRect(area);painter.translate(area.topLeft())
                    canvas._paint_wallpaper(painter,area.size());painter.restore()
            paint_cached_surface(self,p,self.size(),key,draw_wallpaper,layer='wallpaper',
                                 opacity=1-values['background_transparency']/100)
        p.end()


def themed_style(accent='#cebafa',config=None):
    import re
    if not isinstance(accent,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',accent):accent='#cebafa'
    return appearance_style(accent,config)


def control_accent(widget):
    """Use the saved accent for painted controls as well as stylesheet controls."""
    import re
    config=config_for(widget)
    value=effective_accent(config or {})
    return value if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) else '#cebafa'


class SettingsComboBox(ChoiceComboBox):
    """Right-aligned setting value with the shared choice popup."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setProperty('choiceAlignRight',True)


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
        self.hover_animation.stop();self.hover_animation.setDuration(max(1,int(preference(config_for(self),'animation_duration',200))));self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(1.0);self.hover_animation.start();super().enterEvent(event)

    def leaveEvent(self,event):
        if not motion_enabled(self):self.hover_animation.stop();self._hover_changed(0.0);return super().leaveEvent(event)
        self.hover_animation.stop();self.hover_animation.setDuration(max(1,int(preference(config_for(self),'animation_duration',200))));self.hover_animation.setStartValue(self.hover_amount);self.hover_animation.setEndValue(0.0);self.hover_animation.start();super().leaveEvent(event)

    def setSubtitle(self,text):
        subtitle=str(text or '')
        if self.subtitle==subtitle and self.height()==row_height(self,68 if subtitle else 48):return
        self.subtitle=subtitle;self.setFixedHeight(row_height(self,68 if self.subtitle else 48))
        self.setToolTip(self.text()+(' · '+self.subtitle if self.subtitle else ''));self.update()

    def text_left(self):return 54

    def sizeHint(self):return QSize(220,row_height(self,68 if self.subtitle else 48))

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds=QRectF(self.rect()).adjusted(10,3,-10,-3)
        if not self.isChecked() and (self.hover_amount or self.hasFocus()):
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(194,220,225,int(20*max(self.hover_amount,float(self.hasFocus()))*surface_opacity(config_for(self)))));painter.drawRoundedRect(bounds,corner(self,7),corner(self,7))
        role='disabled' if not self.isEnabled() else 'selected_text' if self.isChecked() else 'icon'
        color=paint_color(self,role,text=True)
        icon(self.glyph,paint_color(self,role)).paint(painter,22,(self.height()-20)//2,20,20)
        bold=appearance_values(config_for(self))['bold_text']
        font=self.font();font.setPixelSize(text_size(self,14));font.setBold(self.isChecked() or bold);painter.setFont(font);painter.setPen(QColor(color))
        metrics=QFontMetrics(font);width=max(0,self.width()-self.text_left()-16)
        title=metrics.elidedText(self.text(),Qt.TextElideMode.ElideRight,width)
        line_height=max(22,metrics.height()+2);top=(self.height()-line_height-text_size(self,12)-8)/2
        painter.drawText(QRectF(self.text_left(),top if self.subtitle else 0,width,line_height if self.subtitle else self.height()),Qt.AlignmentFlag.AlignVCenter,title)
        if self.subtitle:
            font.setPixelSize(text_size(self,12));font.setBold(bold);painter.setFont(font);painter.setPen(paint_color(self,'muted',text=True))
            subtitle=QFontMetrics(font).elidedText(self.subtitle,Qt.TextElideMode.ElideRight,width)
            painter.drawText(QRectF(self.text_left(),top+line_height+2,width,text_size(self,12)+6),Qt.AlignmentFlag.AlignVCenter,subtitle)
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
 'schematic':[[(3,3),(9,3),(9,9),(3,9),(3,3)],[(15,15),(21,15),(21,21),(15,21),(15,15)],[(6,9),(6,18),(15,18)],[(9,6),(18,6),(18,15)]],
 'image':[[(3,4),(21,4),(21,20),(3,20),(3,4)],[(3,17),(9,11),(14,16),(17,13),(21,17)],[(7,8),(8,8)]],
 'edit':[[(4,16),(15,5),(19,9),(8,20),(3,21),(4,16)],[(13,7),(17,11)]],
 'refresh':[[(20,5),(20,11),(14,11)],[(4,19),(4,13),(10,13)],[(20,11),(18,6),(12,3),(6,6),(4,10)],[(4,13),(6,18),(12,21),(18,18),(20,14)]],
 'tools':[],
 'upload':[[(12,3),(12,15)],[(7,8),(12,3),(17,8)],[(4,16),(4,21),(20,21),(20,16)]],
 'skin':[[(8,3),(16,3),(16,9),(8,9),(8,3)],[(8,10),(16,10),(16,18),(8,18),(8,10)],[(4,10),(7,10),(7,18),(4,18),(4,10)],[(17,10),(20,10),(20,18),(17,18),(17,10)],[(8,18),(8,23),(11,23),(11,18)],[(13,18),(13,23),(16,23),(16,18)]],
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
    if name=='tools':
        # Open-jaw spanner, drawn as one continuous rounded outline.
        path=QPainterPath(QPointF(14.7,6.3))
        path.cubicTo(14.3,6.7,14.3,7.3,14.7,7.7);path.lineTo(16.3,9.3)
        path.cubicTo(16.7,9.7,17.3,9.7,17.7,9.3);path.lineTo(21.1,5.9)
        path.cubicTo(22.7,10.9,18.3,15.3,13.5,13.6);path.lineTo(7.1,20)
        path.cubicTo(5.1,22,2,18.9,4,16.9);path.lineTo(10.4,10.5)
        path.cubicTo(8.7,5.7,13.1,1.3,18.1,2.9);path.closeSubpath()
        painter.drawPath(path)
    if name=='rocket':
        path=QPainterPath(QPointF(8,16));path.cubicTo(8,9,14,3,21,3)
        path.cubicTo(21,10,15,16,8,16);path.closeSubpath();painter.drawPath(path)
        path=QPainterPath(QPointF(8,10));path.lineTo(4,10);path.lineTo(3,16);path.lineTo(8,14)
        path.moveTo(14,16);path.lineTo(14,20);path.lineTo(8,21);path.lineTo(10,16)
        path.moveTo(6,18);path.lineTo(3,21);painter.drawPath(path);painter.drawEllipse(QRectF(13,7,4,4))
    if name in ('search','account','world','history'):
        rect={'search':(3,3,14,14),'account':(8,3,8,8),'world':(2,2,20,20),'history':(3,3,18,18)}[name]
        painter.drawEllipse(QRectF(*rect))
    for points in PATHS.get(name,[] if name=='rocket' else PATHS['package']):
        path=QPainterPath(QPointF(*points[0]))
        for point in points[1:]:path.lineTo(QPointF(*point))
        if name=='play':painter.fillPath(path,QColor(color))
        else:painter.drawPath(path)
    painter.end();image.setDevicePixelRatio(3)
    return QIcon(image)


class WelcomeLine(QLabel):
    """One fitted line, without changing layout geometry during painting."""
    def __init__(self,large=False):
        super().__init__('');self.large=large
        self.setObjectName('heroTitle' if large else 'heroSubtitle')
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.setFixedHeight(60 if large else 28)

    def setText(self,text):
        super().setText(text);self.setToolTip(text)

    def paintEvent(self,event):
        font=QFont(self.font());maximum=44 if self.large else 16
        font.setPixelSize(maximum)
        full=QFontMetrics(font).horizontalAdvance(self.text())
        font.setPixelSize(max(18 if self.large else 12,min(maximum,int(maximum*self.width()/max(1,full)))))
        painter=QPainter(self);painter.setFont(font)
        painter.setPen(paint_color(self,'text' if self.large else 'muted',text=True))
        text=QFontMetrics(font).elidedText(self.text(),Qt.TextElideMode.ElideRight,self.width())
        painter.drawText(self.rect(),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)


class FeedbackLabel(QLabel):
    """Reserve status space only when there is an actual message."""
    def __init__(self):
        super().__init__('');self.setObjectName('muted')
        self.setTextFormat(Qt.TextFormat.PlainText);self.hide()

    def setText(self,text):
        super().setText(text);self.setVisible(bool(text))


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
            if subtitle:heading.setToolTip(subtitle)
        surface=QWidget();surface.setObjectName('settingsSection');self.body=column(surface,0,0);outer.addWidget(surface)


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
        self.motion.setDuration(max(1,int(preference(config_for(self),'animation_duration',200))))
        self.motion.setStartValue(self.position);self.motion.setEndValue(float(checked));self.motion.start()

    def _emphasize(self,target):
        self.thumb_motion.stop()
        if not self.isEnabled():target=0.0
        if not self.isVisible() or not motion_enabled(self):self._resize_thumb(target);return
        self.thumb_motion.setDuration(max(1,int(preference(config_for(self),'animation_duration',200))))
        self.thumb_motion.setStartValue(self.emphasis);self.thumb_motion.setEndValue(target);self.thumb_motion.start()

    def enterEvent(self,event):self._emphasize(1.0);super().enterEvent(event)
    def leaveEvent(self,event):self._emphasize(0.0);super().leaveEvent(event)
    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(surface_opacity(config_for(self)))
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
    def _layout_editor(self):
        self.lineEdit().setGeometry(8,4,max(1,self.width()-16),max(1,self.height()-8))

    def resizeEvent(self,event):
        super().resizeEvent(event);self._layout_editor()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.StyleChange,QEvent.Type.FontChange) and self.lineEdit() is not None:self._layout_editor()


class ContentText(QWidget):
    def __init__(self,title,detail):
        super().__init__();self.title=str(title);self.detail=' '.join(str(detail).split());self.setMinimumWidth(80)
        self.setToolTip(self.title+'\n'+self.detail);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)

    def paintEvent(self,event):
        p=QPainter(self);font=self.font();font.setPixelSize(text_size(self,14))
        large=QFontMetrics(font).height()+2;small=text_size(self,12)+6
        top=max(0,(self.height()-large-small-2)/2)
        p.setFont(font);p.setPen(paint_color(self,'text',text=True))
        p.drawText(QRectF(0,top,self.width(),large),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.title,Qt.TextElideMode.ElideRight,self.width()))
        font.setPixelSize(text_size(self,12));p.setFont(font);p.setPen(paint_color(self,'muted',text=True))
        p.drawText(QRectF(0,top+large+2,self.width(),small),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(self.detail,Qt.TextElideMode.ElideRight,self.width()));p.end()


class ContentCheck(QCheckBox):
    def __init__(self):
        super().__init__();self.setFixedSize(24,28);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self,point):return self.rect().contains(point)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(surface_opacity(config_for(self)))
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

    def apply_appearance(self):
        self.setFixedHeight(row_height(self))
        spacing=6 if preference(config_for(self),'list_density','standard')=='compact' else 10
        self.line.setContentsMargins(10,spacing,10,spacing)

    def showEvent(self,event):
        self.apply_appearance();super().showEvent(event)

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
        super().__init__(parent);self.image=None;self.path=None;self.tile=None;self.config_obj=config;self._source_key=None;self._blur_key=None;self.original_image=None
        self.set_background(path)

    def set_background(self,path):
        path=str(path or '')
        from pathlib import Path
        try:stamp=Path(path).stat().st_mtime_ns if path else 0
        except OSError:stamp=0
        source_key=(path,stamp)
        strength=int(preference(config_for(self),'background_blur',0))
        if self._blur_key==(source_key,strength):return
        if self._source_key==source_key:
            self.image=self.original_image
            self._apply_blur(strength);self._blur_key=(source_key,strength);self.update();return
        self.path=path;self.image=None;self.tile=None;self._source_key=source_key
        if path:
            reader=QImageReader(str(path));size=reader.size()
            if size.isValid() and size.width()*size.height()<=64_000_000:
                if size.width()>3840 or size.height()>2160:reader.setScaledSize(size.scaled(3840,2160,Qt.AspectRatioMode.KeepAspectRatio))
                value=reader.read()
                if not value.isNull():self.image=value;self.tile=QPixmap.fromImage(value)
        self.original_image=self.image
        self._apply_blur(strength);self._blur_key=(source_key,strength)
        self.update()

    def _apply_blur(self,strength):
        if self.image is not None and strength:
            from PySide6.QtWidgets import QGraphicsScene,QGraphicsPixmapItem,QGraphicsBlurEffect
            # Bound native filter work; retain full original for display modes and color extraction.
            source=self.image.scaled(1280,720,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if self.image.width()>1280 or self.image.height()>720 else self.image
            pad=strength*2
            padded=QImage(source.width()+2*pad,source.height()+2*pad,QImage.Format.Format_ARGB32_Premultiplied)
            padded.fill(0);paint=QPainter(padded)
            paint.drawImage(QRect(pad,pad,source.width(),source.height()),source)
            # Replicate edge pixels so the blur cannot introduce a transparent frame.
            for target,region in ((QRect(0,pad,pad,source.height()),QRect(0,0,1,source.height())),
                (QRect(pad+source.width(),pad,pad,source.height()),QRect(source.width()-1,0,1,source.height())),
                (QRect(0,0,padded.width(),pad),QRect(0,0,source.width(),1)),
                (QRect(0,pad+source.height(),padded.width(),pad),QRect(0,source.height()-1,source.width(),1))):paint.drawImage(target,source,region)
            paint.end()
            scene=QGraphicsScene();item=QGraphicsPixmapItem(QPixmap.fromImage(padded));scene.addItem(item)
            effect=QGraphicsBlurEffect();effect.setBlurRadius(strength);effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint);item.setGraphicsEffect(effect)
            result=QImage(source.size(),QImage.Format.Format_ARGB32_Premultiplied);result.fill(0)
            paint=QPainter(result);scene.render(paint,QRectF(result.rect()),QRectF(pad,pad,source.width(),source.height()));paint.end()
            self.image=result.scaled(self.original_image.size(),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.tile=QPixmap.fromImage(self.image) if self.image is not None else None

    def paintEvent(self,event):
        # The shared backdrop owns all wallpaper pixels, including content-only mode.
        # This widget contains foreground controls and never punches a hole in its parent.
        pass

    def resizeEvent(self,event):
        super().resizeEvent(event)
        owner=self.window()
        if hasattr(owner,'centralWidget') and owner.centralWidget() is not None:owner.centralWidget().update()

    def paint_background(self,p,viewport):
        """Composite independent UI and wallpaper layers in one coordinate space."""
        values=appearance_values(config_for(self))
        key=(values['color_mode'],effective_accent(config_for(self)),values['background_transparency'] if self.image is None else 0,preference(config_for(self),'background_mode'),self.image.cacheKey() if self.image is not None else 0)
        paint_cached_surface(self,p,viewport,key,self._paint_ui_background)
        if self.image is not None:
            paint_cached_surface(self,p,viewport,key,self._paint_wallpaper,layer='wallpaper',
                                 opacity=1-values['background_transparency']/100)

    def _paint_ui_background(self,p,viewport):
        p.save()
        rect=QRectF(0,0,viewport.width(),viewport.height())
        values=appearance_values(config_for(self));opacity=1-values['background_transparency']/100
        paint_glass_background(p,viewport,self)
        if self.image is not None:
            p.restore();return
        p.setOpacity(opacity)
        if self.image is None:
            p.save();p.scale(viewport.width()/1000,viewport.height()/700)
            for offset,alpha in ((0,36),(18,18),(42,10)):
                path=QPainterPath(QPointF(-100,480+offset));path.cubicTo(220,80+offset,600,650+offset,1110,120+offset)
                gradient=QLinearGradient(0,0,1000,700)
                gradient.setColorAt(0,QColor(168,139,228,alpha));gradient.setColorAt(.52,QColor(203,184,255,alpha));gradient.setColorAt(1,QColor(207,163,224,alpha))
                p.setPen(QPen(gradient,80 if offset==0 else 1.2));p.drawPath(path)
            p.restore()
        self._paint_shade(p,viewport);p.restore()

    def _paint_wallpaper(self,p,viewport):
        # Wallpaper pixels never inherit UI surface opacity, including their shade.
        p.save();p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect=QRectF(0,0,viewport.width(),viewport.height())
        mode=preference(config_for(self),'background_mode','fill')
        if mode=='tile':p.fillRect(rect,QBrush(self.tile))
        else:p.drawImage(background_rect(self.image.size(),viewport,mode),self.image)
        self._paint_shade(p,viewport);p.restore()

    def _paint_shade(self,p,viewport):
        rect=QRectF(0,0,viewport.width(),viewport.height())
        values=appearance_values(config_for(self))
        shade=QLinearGradient(0,0,0,viewport.height());light=values['color_mode']=='light'
        shade.setColorAt(0,QColor(250,250,255,90) if light else QColor(10,12,20,20))
        shade.setColorAt(1,QColor(246,246,253,190) if light else QColor(13,20,31,140))
        p.fillRect(rect,shade)


def setting_row(layout,title,description,control):
    """A HMCL-style title, explanation and aligned editor row."""
    container=QWidget();container.setObjectName('settingRow');container.setMinimumHeight(58)
    line=row(container,16,20);line.setContentsMargins(16,6,16,6)
    text=label(title,'settingTitle');text.setToolTip(description);text.setMinimumWidth(128);line.addWidget(text,1)
    if isinstance(control,QWidget):
        if isinstance(control,QSpinBox):
            control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);control.setAlignment(Qt.AlignmentFlag.AlignRight);control.setFixedWidth(140)
        elif isinstance(control,QComboBox):control.setFixedWidth(280)
        elif isinstance(control,QLineEdit):
            wide=bool(control.property('wideEditor'));control.setMinimumWidth(360 if wide else 260);control.setMaximumWidth(960 if wide else 680)
            control.setSizePolicy(QSizePolicy.Policy.Expanding if wide else QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed);control.setAlignment(Qt.AlignmentFlag.AlignRight)
        elif isinstance(control,QPushButton):
            control.setProperty('settingAction',True);control.setMinimumWidth(max(140,control.sizeHint().width()+16))
        line.addWidget(control,3 if control.property('wideEditor') else 0)
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


class TaskStageMark(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.state='active';self.setFixedSize(20,22)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor(config_for(self).get('accent_color') or '#cebafa') if self.state=='active' else paint_color(self,'muted')
        painter.setPen(QPen(color,1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        if self.state=='done':
            path=QPainterPath(QPointF(4,11));path.lineTo(8,15);path.lineTo(16,6);painter.drawPath(path)
        elif self.state=='active':
            painter.drawLine(QPointF(4,11),QPointF(16,11));painter.drawLine(QPointF(11,6),QPointF(16,11));painter.drawLine(QPointF(11,16),QPointF(16,11))
        else:
            painter.drawLine(QPointF(6,7),QPointF(14,15));painter.drawLine(QPointF(14,7),QPointF(6,15))


class TaskDialog(QDialog):
    """Compact stage history; progress counts and measured network bytes stay distinct."""
    def __init__(self,parent,title):
        super().__init__(parent);self.setWindowTitle(title);self.resize(660,410);self.setMinimumSize(520,330);self.setModal(True)
        self.body=column(self,22,14)
        self.stages=QScrollArea();self.stages.setWidgetResizable(True);self.stages.setFrameShape(QFrame.Shape.NoFrame)
        self.stage_content=QWidget();self.stage_body=column(self.stage_content,0,6);self.stage_body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.stages.setWidget(self.stage_content);self.body.addWidget(self.stages,1)
        self.rows=[];self.current=None;self.cancelled=False;self.job=None
        self.detail=QWidget();detail=column(self.detail,30,6);detail.setContentsMargins(30,0,0,6)
        self.message=label('准备中…','muted',True);detail.addWidget(self.message)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(5);detail.addWidget(self.progress)
        self.amount=label('','muted');detail.addWidget(self.amount)
        self.stage_body.addWidget(self.detail)
        footer=row();stats=column(spacing=3)
        self.speed=label('0 B/s','muted');self.transferred=label('','muted');stats.addWidget(self.speed);stats.addWidget(self.transferred)
        footer.addLayout(stats,1);self.cancel_button=button('取消',self.cancel_job);footer.addWidget(self.cancel_button,0,Qt.AlignmentFlag.AlignBottom);self.body.addLayout(footer)
        self.samples=deque();self.total_bytes=0;self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.update_speed);self.timer.start()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(paint_color(self,'base'));painter.drawRoundedRect(QRectF(self.rect()),12,12)

    @staticmethod
    def byte_text(value):
        for unit in ('B','KiB','MiB','GiB'):
            if value<1024 or unit=='GiB':return f'{value:.0f} {unit}' if unit=='B' else f'{value:.1f} {unit}'
            value/=1024

    def start_stage(self,text):
        if self.current and self.current[2].text()==text:return
        if self.current:self.current[1].state='done';self.current[1].update()
        item=QWidget();line=row(item,0,8);mark=TaskStageMark();line.addWidget(mark,0,Qt.AlignmentFlag.AlignTop)
        title=label(text,wrap=True);line.addWidget(title,1)
        self.stage_body.removeWidget(self.detail)
        self.stage_body.addWidget(item);self.stage_body.addWidget(self.detail)
        self.current=(item,mark,title);self.rows.append(self.current)
        # Keep a bounded history and never rebuild existing rows on a progress tick.
        if len(self.rows)>80:
            old=self.rows.pop(0)[0];self.stage_body.removeWidget(old);old.hide();old.deleteLater()
        self.message.setText('正在处理…');self.amount.clear();self.progress.setRange(0,0)
        QTimer.singleShot(0,lambda:self.stages.ensureWidgetVisible(self.detail))

    def update_progress(self,value):
        if isinstance(value,dict) and value.get('kind')=='transfer':
            now=time.monotonic();previous=self.total_bytes;self.total_bytes=max(previous,int(value['bytes']))
            if not self.samples:self.samples.append((now-.25,previous))
            self.samples.append((now,self.total_bytes));self.transferred.setText('已接收 '+self.byte_text(self.total_bytes));self.update_speed();return
        if self.cancelled:return
        if isinstance(value,str):self.start_stage(value)
        elif isinstance(value,tuple) and len(value)==2:
            done,total=value
            if total>0:
                fraction=max(0,min(1,done/total));self.progress.setRange(0,1000);self.progress.setValue(round(fraction*1000))
                self.amount.setText(f'{done:,} / {total:,}  ·  {fraction:.0%}')
                self.message.setText('当前阶段已完成' if done>=total else '正在处理…')
            else:self.progress.setRange(0,0);self.amount.setText('')

    def update_speed(self):
        now=time.monotonic()
        while len(self.samples)>1 and now-self.samples[1][0]>1.5:self.samples.popleft()
        speed=0
        if len(self.samples)>1 and now-self.samples[-1][0]<1.5:
            speed=(self.samples[-1][1]-self.samples[0][1])/max(.1,now-self.samples[0][0])
        self.speed.setText(self.byte_text(max(0,speed))+'/s')

    def complete(self,failed=False):
        self.timer.stop()
        if self.current:self.current[1].state='failed' if failed or self.cancelled else 'done';self.current[1].update()

    def cancel_job(self):
        if self.job:self.job.cancel.set()
        self.cancelled=True;self.cancel_button.setEnabled(False);self.message.setText('正在取消，请稍候…')

    def reject(self):
        self.cancel_job()
