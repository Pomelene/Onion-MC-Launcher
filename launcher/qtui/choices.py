"""Shared flat choice popups, preserving QComboBox models and native signals."""
from PySide6.QtCore import Qt,QPoint,QRectF,QSize,QEvent,QSortFilterProxyModel
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QFontMetrics,QPainterPath
from PySide6.QtWidgets import (QFrame,QComboBox,QListView,QLineEdit,QVBoxLayout,
    QStyledItemDelegate,QStyle,QStyleOptionComboBox,QMenu)
from .theme import config_for,paint_color,surface_opacity,appearance_values,contrasting_accent,effective_accent,corner,text_size,row_height,preference


def accent_for(widget):
    color=QColor(effective_accent(config_for(widget)))
    return color if color.isValid() else QColor('#cebafa')


def paint_popup(widget,painter,radius=12):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill=paint_color(widget,'surface');factor=surface_opacity(config_for(widget));fill.setAlpha(round(252*factor))
    border=paint_color(widget,'icon');border.setAlpha(round(50*factor))
    painter.setPen(QPen(border,1));painter.setBrush(fill)
    painter.drawRoundedRect(QRectF(widget.rect()).adjusted(.5,.5,-.5,-.5),corner(widget,radius),corner(widget,radius))


class ChoiceDelegate(QStyledItemDelegate):
    def __init__(self,popup):super().__init__(popup);self.popup=popup

    def sizeHint(self,option,index):
        return QSize(240,14 if index.data(Qt.ItemDataRole.AccessibleDescriptionRole)=='separator' else row_height(self.popup.owner,42))

    def paint(self,painter,option,index):
        owner=self.popup.owner;painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(2,2,-2,-2)
        if index.data(Qt.ItemDataRole.AccessibleDescriptionRole)=='separator':
            color=paint_color(owner,'icon');color.setAlpha(35);painter.setPen(QPen(color,1))
            painter.drawLine(QPoint(int(rect.left()+10),int(rect.center().y())),QPoint(int(rect.right()-10),int(rect.center().y())))
            painter.restore();return
        source=self.popup.proxy.mapToSource(index);chosen=source.row()==owner.currentIndex()
        enabled=bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        if chosen or option.state & (QStyle.StateFlag.State_Selected|QStyle.StateFlag.State_MouseOver):
            color=accent_for(owner);color.setAlpha(round((42 if chosen else 22)*surface_opacity(config_for(owner))))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color);painter.drawRoundedRect(rect,corner(owner,8),corner(owner,8))
        font=QFont(owner.font())
        if chosen or appearance_values(config_for(owner))['bold_text']:font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font);painter.setPen(paint_color(owner,'text' if enabled else 'disabled',text=True))
        text_rect=rect.adjusted(12,0,-32,0);decoration=index.data(Qt.ItemDataRole.DecorationRole)
        if decoration is not None and hasattr(decoration,'paint'):
            decoration.paint(painter,int(text_rect.left()),int(rect.center().y()-9),18,18);text_rect.adjust(26,0,0,0)
        painter.drawText(text_rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(font).elidedText(str(index.data() or ''),Qt.TextElideMode.ElideRight,int(text_rect.width())))
        if chosen:
            color=QColor(contrasting_accent(accent_for(owner).name(),appearance_values(config_for(owner))['color_mode']))
            painter.setPen(QPen(color,1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            x=rect.right()-16;y=rect.center().y();path=QPainterPath();path.moveTo(x-5,y);path.lineTo(x-1,y+4);path.lineTo(x+6,y-4);painter.drawPath(path)
        painter.restore()


class ChoicePopup(QFrame):
    def __init__(self,owner):
        super().__init__(owner,Qt.WindowType.Popup|Qt.WindowType.FramelessWindowHint)
        self.owner=owner;self.setObjectName('choicePopup');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay,True)
        body=QVBoxLayout(self);body.setContentsMargins(8,8,8,8);body.setSpacing(6)
        self.search=QLineEdit(self);self.search.setObjectName('choiceSearch');self.search.setPlaceholderText('搜索选项');self.search.setClearButtonEnabled(True);body.addWidget(self.search)
        self.proxy=QSortFilterProxyModel(self);self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list=QListView(self);self.list.setObjectName('choiceList');self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.list.setUniformItemSizes(False)
        self.list.setModel(self.proxy);self.list.setItemDelegate(ChoiceDelegate(self));body.addWidget(self.list,1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.list.clicked.connect(self.choose);self.list.installEventFilter(self);self.search.installEventFilter(self)
        self.search.returnPressed.connect(lambda:self.choose(self.list.currentIndex()) if self.list.currentIndex().isValid() else self.choose(self.proxy.index(0,0)))

    def paintEvent(self,event):
        p=QPainter(self);paint_popup(self,p);p.end()

    def hideEvent(self,event):
        super().hideEvent(event);QComboBox.hidePopup(self.owner);self.owner.update()

    def choose(self,index):
        if not index.isValid() or not index.flags() & Qt.ItemFlag.ItemIsEnabled:return
        if index.data(Qt.ItemDataRole.AccessibleDescriptionRole)=='separator':return
        source=self.proxy.mapToSource(index);row=source.row();self.owner.setCurrentIndex(row)
        self.owner.activated.emit(row);self.owner.textActivated.emit(self.owner.itemText(row))
        self.owner.hidePopup();self.owner.setFocus(Qt.FocusReason.PopupFocusReason)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.KeyPress:
            if event.key()==Qt.Key.Key_Escape:self.owner.hidePopup();return True
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and watched is self.list:self.choose(self.list.currentIndex());return True
            if event.key()==Qt.Key.Key_Down and watched is self.search:
                self.list.setFocus();self.list.setCurrentIndex(self.proxy.index(0,0));return True
        return super().eventFilter(watched,event)

    def open(self):
        owner=self.owner;self.proxy.setSourceModel(owner.model());self.proxy.setFilterKeyColumn(owner.modelColumn())
        self.list.setModelColumn(owner.modelColumn());self.list.setRootIndex(self.proxy.mapFromSource(owner.rootModelIndex()))
        self.search.clear();searchable=owner.count()>12;self.search.setVisible(searchable)
        font=QFontMetrics(owner.font());longest=max((font.horizontalAdvance(owner.itemText(i)) for i in range(owner.count())),default=0)
        screen=owner.screen().availableGeometry();width=min(max(owner.width(),longest+72,240),560,screen.width()-16)
        wanted=min(8,max(1,owner.count()))*42+16+(44 if searchable else 0)
        below=owner.mapToGlobal(QPoint(0,owner.height()+6));above=owner.mapToGlobal(QPoint(0,-6))
        room_below=screen.bottom()-below.y()-8;room_above=above.y()-screen.top()-8
        use_below=room_below>=wanted or room_below>=room_above
        height=min(wanted,max(60,room_below if use_below else room_above))
        x=below.x()+owner.width()-width if owner.property('choiceAlignRight') else below.x()
        x=max(screen.left()+8,min(x,screen.right()-width-8))
        y=below.y() if use_below else above.y()-height;y=max(screen.top()+8,min(y,screen.bottom()-height-8))
        self.resize(width,height);self.move(x,y)
        selected=self.proxy.mapFromSource(owner.model().index(owner.currentIndex(),owner.modelColumn(),owner.rootModelIndex()))
        self.list.setCurrentIndex(selected);self.show();self.list.scrollTo(selected)
        (self.search if searchable else self.list).setFocus(Qt.FocusReason.PopupFocusReason);owner.update()


class ChoiceComboBox(QComboBox):
    def __init__(self,parent=None):
        super().__init__(parent);self.choice_popup=None;self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showPopup(self):
        if not self.count() or not self.isEnabled():return
        if self.choice_popup is None:self.choice_popup=ChoicePopup(self)
        self.choice_popup.open()

    def hidePopup(self):
        if self.choice_popup is not None:self.choice_popup.hide()
        super().hidePopup();self.update()

    def mousePressEvent(self,event):
        if self.choice_popup is not None and self.choice_popup.isVisible() and event.button()==Qt.MouseButton.LeftButton:
            self.hidePopup();event.accept();return
        super().mousePressEvent(event)

    def paintEvent(self,event):
        option=QStyleOptionComboBox();self.initStyleOption(option)
        option.subControls=QStyle.SubControl.SC_ComboBoxFrame
        p=QPainter(self);self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox,option,p,self)
        rect=QRectF(self.rect()).adjusted(12,0,-32,0)
        color=option.palette.color(self.foregroundRole());p.setPen(color);p.setFont(self.font())
        decoration=self.itemIcon(self.currentIndex())
        if not decoration.isNull():decoration.paint(p,int(rect.left()),int(rect.center().y()-9),18,18);rect.adjust(26,0,0,0)
        alignment=Qt.AlignmentFlag.AlignRight if self.property('choiceAlignRight') else Qt.AlignmentFlag.AlignLeft
        p.drawText(rect,alignment|Qt.AlignmentFlag.AlignVCenter,QFontMetrics(self.font()).elidedText(self.currentText(),Qt.TextElideMode.ElideRight,int(rect.width())))
        p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(color,1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x=self.width()-17;y=self.height()/2;opened=self.choice_popup is not None and self.choice_popup.isVisible()
        path=QPainterPath();path.moveTo(x-4,y+(2 if opened else -2));path.lineTo(x,y+(-2 if opened else 2));path.lineTo(x+4,y+(2 if opened else -2));p.drawPath(path);p.end()


class ActionMenu(QMenu):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)

    def paintEvent(self,event):
        p=QPainter(self);paint_popup(self,p);p.end();super().paintEvent(event)
