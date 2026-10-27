"""Content-first lists with explicit, theme-aware painting in every state."""
from PySide6.QtCore import Qt,QSize,QRect
from PySide6.QtGui import QFont,QFontMetrics,QIcon,QColor
from PySide6.QtWidgets import QTreeWidget,QStyledItemDelegate,QStyle,QAbstractItemView,QFrame,QHeaderView
from .theme import config_for,preference,text_size,paint_color,effective_accent,surface_opacity

DETAIL_ROLE=Qt.ItemDataRole.UserRole+40
META_ROLE=Qt.ItemDataRole.UserRole+41


class FlatListDelegate(QStyledItemDelegate):
    def fonts(self):
        widget=self.parent();font=QFont(widget.font());font.setPixelSize(text_size(widget,14))
        font.setWeight(QFont.Weight.DemiBold if preference(config_for(widget),'bold_text',False) else QFont.Weight.Normal)
        small=QFont(font);small.setPixelSize(text_size(widget,12));small.setWeight(QFont.Weight.Normal)
        return font,small

    def sizeHint(self,option,index):
        font,small=self.fonts();detail=index.data(DETAIL_ROLE) if index.column()==0 else None
        height=QFontMetrics(font).height()+22
        if detail:height+=QFontMetrics(small).height()+3
        return QSize(100,max(44,height))

    def paint(self,painter,option,index):
        widget=self.parent();config=config_for(widget);painter.save();painter.setClipRect(option.rect)
        # Native HighlightedText can turn black under a translucent stylesheet.
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            tint=QColor(effective_accent(config));tint.setAlphaF((.13 if selected else .055)*surface_opacity(config));painter.fillRect(option.rect,tint)
        rect=option.rect.adjusted(14,0,-14,0)
        font,small=self.fonts();detail=index.data(DETAIL_ROLE) if index.column()==0 else None
        meta=str(index.data(META_ROLE) or '') if index.column()==0 else ''
        title=str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        decoration=index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(decoration,QIcon) and not decoration.isNull():
            size=text_size(widget,24);decoration.paint(painter,rect.left(),rect.center().y()-size//2,size,size);rect.adjust(size+12,0,0,0)
        foreground=paint_color(widget,'text' if option.state & QStyle.StateFlag.State_Enabled else 'disabled',text=True)
        muted=paint_color(widget,'muted',text=True)
        if meta:
            metrics=QFontMetrics(small);width=min(metrics.horizontalAdvance(meta),max(0,rect.width()//3))
            painter.setFont(small);painter.setPen(muted)
            painter.drawText(QRect(rect.right()-width+1,rect.top(),width,rect.height()),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(meta,Qt.TextElideMode.ElideRight,width))
            rect.adjust(0,0,-width-18,0)
        total=QFontMetrics(font).height()+(QFontMetrics(small).height()+3 if detail else 0)
        top=rect.top()+(rect.height()-total)//2
        lines=[(title,font,foreground)]
        if detail:lines.append((str(detail),small,muted))
        for text,current,color in lines:
            metrics=QFontMetrics(current);painter.setFont(current);painter.setPen(color)
            painter.drawText(QRect(rect.left(),top,max(0,rect.width()),metrics.height()),Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(text,Qt.TextElideMode.ElideRight,max(0,rect.width())))
            top+=metrics.height()+3
        if option.state & QStyle.StateFlag.State_HasFocus:
            mark=QColor(effective_accent(config));mark.setAlphaF(surface_opacity(config));painter.fillRect(QRect(option.rect.left(),option.rect.center().y()-8,2,16),mark)
        painter.restore()


class FlatTreeWidget(QTreeWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setProperty('listSurface',True)
        self.setFrameShape(QFrame.Shape.NoFrame);self.setRootIsDecorated(False);self.setIndentation(0)
        self.setHeaderHidden(True);self.setUniformRowHeights(False);self.setAlternatingRowColors(False);self.setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight);self.setItemDelegate(FlatListDelegate(self))
        self.viewport().setAutoFillBackground(False)

    def entities(self,actions=0):
        self.setColumnCount(1+actions);self.setHeaderHidden(True);self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in range(1,1+actions):self.header().setSectionResizeMode(column,QHeaderView.ResizeMode.Fixed);self.setColumnWidth(column,40)
