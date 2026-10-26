"""Compact HSV picker with explicit, reversible colour selection."""
import re

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QLinearGradient
from PySide6.QtWidgets import (QWidget, QDialog, QSlider, QLineEdit, QHBoxLayout,
    QVBoxLayout, QGridLayout, QAbstractButton)
from .theme import paint_color, config_for, surface_opacity,corner
from .widgets import label, button, InlineSpinBox


class ColorSwatch(QAbstractButton):
    def __init__(self, color, parent=None, size=30):
        super().__init__(parent)
        self.color=QColor(color);self.selected=False;self.setFixedSize(size,size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.color.name());self.setAccessibleName(self.color.name())

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect()).adjusted(3,3,-3,-3)
        edge=paint_color(self,'text');edge.setAlpha(40)
        p.setPen(QPen(edge,1));p.setBrush(self.color);p.drawRoundedRect(r,corner(self,7),corner(self,7))
        if self.selected or self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(paint_color(self,'text'),1.5))
            radius=corner(self,7)+2 if corner(self,7) else 0
            p.drawRoundedRect(r.adjusted(-2,-2,2,2),radius,radius)
        p.end()


class SaturationValue(QWidget):
    changed=Signal(float,float)

    def __init__(self,parent=None):
        super().__init__(parent);self.hue=258;self.saturation=0.;self.value=1.
        self.setMinimumSize(360,210);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor);self.setAccessibleName('饱和度与明度，方向键调整，Shift 加速')

    def area(self):return QRectF(self.rect()).adjusted(7,7,-7,-7)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);r=self.area()
        clip=QPainterPath();clip.addRoundedRect(r,corner(self,10),corner(self,10));p.setClipPath(clip)
        gradient=QLinearGradient(r.topLeft(),r.topRight())
        gradient.setColorAt(0,QColor('white'));gradient.setColorAt(1,QColor.fromHsv(self.hue,255,255))
        p.fillRect(r,gradient)
        shade=QLinearGradient(r.topLeft(),r.bottomLeft());shade.setColorAt(0,QColor(0,0,0,0));shade.setColorAt(1,QColor('black'))
        p.fillRect(r,shade);p.setClipping(False)
        center=QPointF(r.left()+r.width()*self.saturation,r.top()+r.height()*(1-self.value))
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(0,0,0,160),4));p.drawEllipse(center,6,6)
        p.setPen(QPen(QColor('white'),2));p.drawEllipse(center,6,6);p.end()

    def select(self,position):
        r=self.area();self.saturation=max(0.,min(1.,(position.x()-r.left())/r.width()))
        self.value=max(0.,min(1.,1-(position.y()-r.top())/r.height()))
        self.changed.emit(self.saturation,self.value);self.update()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.setFocus();self.select(event.position());event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton:self.select(event.position());event.accept()
        else:super().mouseMoveEvent(event)

    def keyPressEvent(self,event):
        step=.05 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else .01
        ds,dv={Qt.Key.Key_Left:(-step,0),Qt.Key.Key_Right:(step,0),Qt.Key.Key_Up:(0,step),Qt.Key.Key_Down:(0,-step)}.get(event.key(),(0,0))
        if ds or dv:
            self.saturation=max(0.,min(1.,self.saturation+ds));self.value=max(0.,min(1.,self.value+dv))
            self.changed.emit(self.saturation,self.value);self.update();event.accept()
        else:super().keyPressEvent(event)


class HueSlider(QSlider):
    def __init__(self,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent);self.setRange(0,359);self.setFixedHeight(28)
        self.setAccessibleName('色相');self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect()).adjusted(10,7,-10,-7);g=QLinearGradient(r.topLeft(),r.topRight())
        for i in range(7):g.setColorAt(i/6,QColor.fromHsv(round(i/6*359),255,255))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(g);p.drawRoundedRect(r,7,7)
        x=r.left()+r.width()*self.value()/359
        p.setBrush(QColor.fromHsv(self.value(),255,255));p.setPen(QPen(QColor(0,0,0,130),4));p.drawEllipse(QPointF(x,r.center().y()),8,8)
        p.setPen(QPen(QColor('white'),2));p.drawEllipse(QPointF(x,r.center().y()),8,8);p.end()

    def select(self,event):
        self.setValue(round(max(0.,min(1.,(event.position().x()-10)/max(1,self.width()-20)))*359));event.accept()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.setFocus();self.select(event)
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton:self.select(event)
        else:super().mouseMoveEvent(event)


class ColorPicker(QDialog):
    PRESETS=('#cebafa','#a78bfa','#818cf8','#60a5fa','#22d3ee','#34d399',
             '#a3e635','#facc15','#fb923c','#f87171','#f472b6','#e2e8f0')

    def __init__(self,color,parent=None):
        super().__init__(parent);self.setWindowTitle('选择特征色');self.setObjectName('colorPicker')
        self.original=QColor(color) if QColor(color).isValid() else QColor('#cebafa')
        self.color=QColor(self.original);self.hue=258
        self.setFixedWidth(540)
        body=QVBoxLayout(self);body.setContentsMargins(22,16,22,20);body.setSpacing(12)
        self.plane=SaturationValue(self);body.addWidget(self.plane)
        self.hue_slider=HueSlider(self);body.addWidget(self.hue_slider)
        presets=QHBoxLayout();presets.setSpacing(8);self.swatches=[]
        for value in self.PRESETS:
            swatch=ColorSwatch(value,self);swatch.clicked.connect(lambda checked=False,c=value:self.set_color(QColor(c)))
            presets.addWidget(swatch);self.swatches.append(swatch)
        presets.addStretch();body.addLayout(presets)
        values=QHBoxLayout();values.setSpacing(16)
        self.original_swatch=ColorSwatch(self.original,self,44);self.original_swatch.setAccessibleName('恢复原颜色')
        self.original_swatch.setToolTip('恢复原颜色');self.original_swatch.clicked.connect(lambda:self.set_color(self.original))
        self.preview=ColorSwatch(self.color,self,44);self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        samples=QVBoxLayout();samples.setSpacing(3);samples.setContentsMargins(0,0,0,0)
        sample_row=QHBoxLayout();sample_row.setSpacing(3);sample_row.addWidget(self.original_swatch);sample_row.addWidget(self.preview)
        samples.addLayout(sample_row);samples.addWidget(label('原色 / 新色','muted'),0,Qt.AlignmentFlag.AlignHCenter)
        values.addLayout(samples)
        fields=QGridLayout();fields.setHorizontalSpacing(10);fields.setVerticalSpacing(6)
        self.hex=QLineEdit();self.hex.setMaxLength(7);self.hex.setAccessibleName('HEX 颜色');self.hex.setFixedHeight(36)
        self.hex.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fields.addWidget(label('HEX','muted'),0,0);fields.addWidget(self.hex,1,0)
        self.rgb=[]
        for column,title in enumerate(('R','G','B'),1):
            field=InlineSpinBox();field.setRange(0,255);field.setFixedSize(66,36)
            field.setAlignment(Qt.AlignmentFlag.AlignCenter);field.setButtonSymbols(InlineSpinBox.ButtonSymbols.NoButtons)
            field.setAccessibleName({'R':'红色','G':'绿色','B':'蓝色'}[title]);fields.addWidget(label(title,'muted'),0,column)
            fields.addWidget(field,1,column);self.rgb.append(field);field.valueChanged.connect(self.rgb_changed)
        fields.setColumnStretch(0,1);values.addLayout(fields,1);body.addLayout(values)
        self.error=label('','muted');self.error.setFixedHeight(18);body.addWidget(self.error)
        footer=QHBoxLayout();footer.addStretch();footer.setSpacing(10)
        self.cancel=button('取消',self.reject,'soft');self.confirm=button('应用颜色',self.accept,'primary')
        for control in (self.cancel,self.confirm):control.setMinimumWidth(100);control.setFixedHeight(38);footer.addWidget(control)
        self.confirm.setDefault(True);body.addLayout(footer)
        self.plane.changed.connect(self.sv_changed);self.hue_slider.valueChanged.connect(self.hue_changed)
        self.hex.textEdited.connect(self.hex_changed);self.hex.editingFinished.connect(self.finish_hex)
        self.set_color(self.color);self.setTabOrder(self.hex,self.rgb[0])

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=paint_color(self,'base');color.setAlpha(round(255*surface_opacity(config_for(self))))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(color);p.drawRoundedRect(QRectF(self.rect()),corner(self,12),corner(self,12));p.end()

    def set_color(self,color,update_hex=True):
        if not color.isValid():return
        self.color=QColor(color)
        hue=self.color.hsvHue()
        if hue>=0:self.hue=hue
        self.plane.hue=self.hue;self.plane.saturation=self.color.hsvSaturationF();self.plane.value=self.color.valueF();self.plane.update()
        with QSignalBlocker(self.hue_slider):self.hue_slider.setValue(self.hue)
        for field,value in zip(self.rgb,self.color.getRgb()[:3]):
            with QSignalBlocker(field):field.setValue(value)
        if update_hex:self.hex.setText(self.color.name())
        self.preview.color=QColor(self.color);self.preview.update();self.preview.setToolTip(self.color.name())
        for swatch in self.swatches:swatch.selected=swatch.color.rgb()==self.color.rgb();swatch.update()
        self.confirm.setEnabled(True);self.error.setText('')

    def sv_changed(self,saturation,value):self.set_color(QColor.fromHsvF(self.hue/360,saturation,value))

    def hue_changed(self,hue):
        self.hue=hue;self.set_color(QColor.fromHsvF(hue/360,self.plane.saturation,self.plane.value))

    def rgb_changed(self,*args):self.set_color(QColor(*(field.value() for field in self.rgb)))

    def hex_changed(self,text):
        valid=bool(re.fullmatch(r'#?[0-9a-fA-F]{6}',text))
        self.confirm.setEnabled(valid);self.error.setText('' if valid else '请输入 6 位十六进制颜色')
        if valid:self.set_color(QColor('#'+text.lstrip('#')),update_hex=False)

    def finish_hex(self):
        if self.confirm.isEnabled():self.hex.setText(self.color.name())

    def accept(self):
        self.hex_changed(self.hex.text())
        if self.confirm.isEnabled():super().accept()
