"""Shared flat tables and two-line entity rows, without nested card chrome."""
from PySide6.QtCore import Qt,QSize,QRect,QEvent
from PySide6.QtGui import QFont,QFontMetrics,QIcon,QColor
from PySide6.QtWidgets import QTreeWidget,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QAbstractItemView,QFrame
from .theme import config_for,preference,text_size,paint_color,effective_accent,surface_opacity

DETAIL_ROLE=Qt.ItemDataRole.UserRole+40


class FlatListDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        widget=self.parent();font=QFont(widget.font());font.setPixelSize(text_size(widget,14))
        height=QFontMetrics(font).height()+20
        if index.column()==0 and index.data(DETAIL_ROLE) is not None:
            small=QFont(font);small.setPixelSize(text_size(widget,12));height+=QFontMetrics(small).height()+4
        return QSize(120,max(44,height))

    def paint(self,painter,option,index):
        detail=index.data(DETAIL_ROLE) if index.column()==0 else None
        if detail is None:return super().paint(painter,option,index)
        widget=self.parent();styled=QStyleOptionViewItem(option);self.initStyleOption(styled,index)
        title=styled.text;decoration=QIcon(styled.icon);styled.text='';styled.icon=QIcon()
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,styled,painter,widget)
        painter.save();rect=option.rect.adjusted(12,0,-12,0)
        if option.state & QStyle.StateFlag.State_Selected:
            color=QColor(effective_accent(config_for(widget)));color.setAlphaF(surface_opacity(config_for(widget)))
            painter.fillRect(QRect(option.rect.left(),option.rect.center().y()-10,2,20),color)
        if not decoration.isNull():
            decoration.paint(painter,rect.left(),rect.center().y()-14,28,28);rect.adjust(40,0,0,0)
        font=QFont(widget.font());font.setPixelSize(text_size(widget,14))
        font.setWeight(QFont.Weight.DemiBold if preference(config_for(widget),'bold_text',False) else QFont.Weight.Normal)
        small=QFont(font);small.setPixelSize(text_size(widget,12))
        top=(rect.height()-QFontMetrics(font).height()-QFontMetrics(small).height()-4)//2+rect.top()
        for text,current,color in ((title,font,'text'),(str(detail),small,'muted')):
            painter.setFont(current);painter.setPen(paint_color(widget,color,text=True));height=QFontMetrics(current).height()
            painter.drawText(QRect(rect.left(),top,rect.width(),height),Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(current).elidedText(text,Qt.TextElideMode.ElideRight,max(0,rect.width())))
            top+=height+4
        painter.restore()


class FlatTreeWidget(QTreeWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame);self.setRootIsDecorated(False);self.setIndentation(0)
        self.setUniformRowHeights(True);self.setAlternatingRowColors(False);self.setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setTextElideMode(Qt.TextElideMode.ElideRight);self.setItemDelegate(FlatListDelegate(self))
        self.header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.header().setMinimumSectionSize(48);self.refresh_header()

    def refresh_header(self):self.header().setFixedHeight(max(30,self.fontMetrics().height()+14))

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self.refresh_header()
