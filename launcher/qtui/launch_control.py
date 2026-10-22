"""Homepage split launch action with a continuous silhouette and stable layout."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QFont,QFontMetrics,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QWidget,QHBoxLayout
from .motion import MotionButton
from .theme import config_for,appearance_values,surface_opacity


class LaunchSegment(MotionButton):
    def __init__(self,parent,quick=False):
        super().__init__('',parent);self.quick=quick
        self.setProperty('role','primary');self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(52 if quick else 300,76)
        self.setAccessibleName('快捷选择实例' if quick else '启动游戏')
        if quick:self.setToolTip('快捷选择实例')

    def setText(self,text):
        super().setText(text)
        self.setAccessibleName(text.replace('\n','，'));self.setToolTip(text.replace('\n',' · '))

    def paintEvent(self,event):
        config=config_for(self);accent=QColor(config.get('accent_color') or '#cebafa')
        if not accent.isValid():accent=QColor('#cebafa')
        ink=QColor('#281f35' if accent.lightnessF()>.55 else '#ffffff')
        factor=surface_opacity(config);accent.setAlpha(round(255*factor))
        ink.setAlpha(round(255*(1-appearance_values(config)['text_transparency']/100)))
        if not self.isEnabled():ink.setAlpha(round(ink.alpha()*.35))
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Both hit regions paint the same whole outline. Neither half scales its fill.
        outline=QPainterPath();outline.addRoundedRect(QRectF(.5-self.x(),.5,self.parentWidget().width()-1,self.height()-1),16,16)
        painter.setClipPath(outline);painter.fillPath(outline,accent)
        if self.isEnabled():
            overlay=QColor('#ffffff' if accent.lightnessF()<.55 else '#352447')
            overlay.setAlpha(round(255*(.055*self.hover_amount+.055*self.press_amount)*factor))
            painter.fillRect(self.rect(),overlay)
        if self.quick:
            separator=QColor(ink);separator.setAlpha(round(38*factor))
            painter.setPen(QPen(separator,1));painter.drawLine(0,20,0,56)
        painter.save();center=self.rect().center();scale=1-.015*self.press_amount
        painter.translate(center);painter.scale(scale,scale);painter.translate(-center)
        if self.quick:
            painter.setPen(QPen(ink,1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath();path.moveTo(21,41);path.lineTo(26,36);path.lineTo(31,41);painter.drawPath(path)
        else:
            from .widgets import icon
            title,_,subtitle=self.text().partition('\n')
            glyph='plus' if title=='安装游戏' else 'rocket'
            signature=(glyph,ink.rgba())
            if getattr(self,'_launch_icon_signature',None)!=signature:
                self._launch_icon_signature=signature;self._launch_icon=icon(glyph,ink)
            self._launch_icon.paint(painter,23,26,24,24)
            x=62;width=self.width()-x-22
            font=QFont(self.font());font.setPixelSize(18);font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font);painter.setPen(ink)
            painter.drawText(QRectF(x,16,width,25),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                             QFontMetrics(font).elidedText(title,Qt.TextElideMode.ElideRight,width))
            font.setPixelSize(12);font.setWeight(QFont.Weight.DemiBold if appearance_values(config)['bold_text'] else QFont.Weight.Normal);painter.setFont(font)
            detail=QColor(ink);detail.setAlpha(round(ink.alpha()*.78));painter.setPen(detail)
            painter.drawText(QRectF(x,42,width,18),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                             QFontMetrics(font).elidedText(subtitle,Qt.TextElideMode.ElideRight,width))
        painter.restore()
        if self.hasFocus():
            focus=QColor(ink);focus.setAlpha(130);painter.setPen(QPen(focus,1,Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(QRectF(5,5,self.width()-10,self.height()-10),11,11)


class LaunchControl(QWidget):
    def __init__(self,launch,select):
        super().__init__();self.setObjectName('startPanel');self.setFixedSize(352,76)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.launch=LaunchSegment(self);self.quick=LaunchSegment(self,True)
        self.launch.clicked.connect(lambda:launch());self.quick.clicked.connect(lambda:select())
        layout.addWidget(self.launch);layout.addWidget(self.quick)
