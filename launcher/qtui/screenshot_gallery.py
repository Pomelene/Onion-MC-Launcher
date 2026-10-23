"""Continuous thumbnail grid with bounded, viewport-driven image decoding."""
from collections import OrderedDict
from datetime import datetime
from PySide6.QtCore import Qt,QAbstractListModel,QModelIndex,QSize,QTimer,QPoint,QRectF
from PySide6.QtGui import QPainter,QPen,QFont,QFontMetrics,QColor
from PySide6.QtWidgets import QListView,QAbstractItemView,QStyledItemDelegate,QStyle
from shiboken6 import isValid
from .theme import paint_color,config_for,surface_opacity
from .widgets import icon,control_accent
from .choices import ActionMenu


class ScreenshotModel(QAbstractListModel):
    def __init__(self,parent):
        super().__init__(parent);self.entries=[];self.cache=OrderedDict();self.generation=0
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.entries)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.entries):return None
        entry=self.entries[index.row()]
        if role==Qt.ItemDataRole.DisplayRole:return entry.path.name
        if role==Qt.ItemDataRole.ToolTipRole:return entry.path.name+'\n'+datetime.fromtimestamp(entry.modified).strftime('%Y-%m-%d %H:%M:%S')
        if role==Qt.ItemDataRole.UserRole:return entry
    def replace(self,entries):
        self.beginResetModel();self.entries=entries;self.generation+=1;self.cache.clear();self.endResetModel()
    def key(self,entry):return (str(entry.path),entry.modified,entry.size)
    def image(self,entry):
        key=self.key(entry)
        if key in self.cache:self.cache.move_to_end(key)
        return self.cache.get(key)


class ScreenshotDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return self.parent().gridSize()
    def paint(self,painter,option,index):
        view=self.parent();entry=index.data(Qt.ItemDataRole.UserRole)
        if entry is None:return
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(4,4,-4,-4)
        selected=bool(option.state & QStyle.StateFlag.State_Selected);hover=bool(option.state & QStyle.StateFlag.State_MouseOver)
        background=paint_color(view,'surface');background.setAlpha(round((210 if selected else 155 if hover else 95)*surface_opacity(config_for(view))))
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(background);painter.drawRoundedRect(rect,9,9)
        if selected:
            painter.setPen(QPen(QColor(control_accent(view)),1.3));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(rect.adjusted(1,1,-1,-1),9,9)
        photo=rect.adjusted(6,6,-6,-47)
        image=view.gallery_model.image(entry)
        if image is not None and not image.isNull():
            size=image.size().scaled(photo.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRectF(photo.center().x()-size.width()/2,photo.center().y()-size.height()/2,size.width(),size.height())
            painter.drawImage(target,image)
        else:
            glyph='folder' if entry.directory else 'image';icon(glyph,paint_color(view,'muted')).paint(painter,int(photo.center().x()-16),int(photo.center().y()-16),32,32)
        width=int(rect.width()-18);font=QFont(view.font());font.setPixelSize(12);painter.setFont(font)
        painter.setPen(paint_color(view,'text',text=True))
        painter.drawText(QRectF(rect.left()+9,rect.bottom()-43,width,20),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(entry.path.name,Qt.TextElideMode.ElideRight,width))
        font.setPixelSize(11);painter.setFont(font);painter.setPen(paint_color(view,'muted',text=True))
        detail='文件夹' if entry.directory else datetime.fromtimestamp(entry.modified).strftime('%m-%d %H:%M:%S')+f'  ·  {entry.size/1024:.0f} KiB'
        painter.drawText(QRectF(rect.left()+9,rect.bottom()-23,width,18),Qt.AlignmentFlag.AlignVCenter,detail)
        painter.restore()


class ScreenshotGallery(QListView):
    def __init__(self,browser):
        super().__init__(browser);self.browser=browser;self.loading=False
        self.gallery_model=ScreenshotModel(self);self.setModel(self.gallery_model)
        self.setViewMode(QListView.ViewMode.IconMode);self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True);self.setResizeMode(QListView.ResizeMode.Adjust);self.setMovement(QListView.Movement.Static)
        self.setGridSize(QSize(224,181));self.setUniformItemSizes(True);self.setSpacing(0)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel);self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.setMouseTracking(True)
        self.setMinimumHeight(360);self.setStyleSheet('QListView { background: transparent; border: none; outline: none; }')
        self.setItemDelegate(ScreenshotDelegate(self));self.setAccessibleName('截图图库，按时间倒序连续显示')
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(30);self.timer.timeout.connect(self.load_visible)
        self.verticalScrollBar().valueChanged.connect(self.schedule)
        self.activated.connect(self.open_index)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.customContextMenuRequested.connect(self.context)

    def replace(self,entries):self.gallery_model.replace(entries);self.scrollToTop();self.schedule()
    def schedule(self,*args):
        if not self.timer.isActive():self.timer.start()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        available=max(120,self.viewport().width()-16)
        columns=max(1,available//205);width=max(120,available//columns)
        size=QSize(width,round((width-20)*9/16)+54)
        if self.gridSize()!=size:self.setGridSize(size)
        self.schedule()
    def showEvent(self,event):super().showEvent(event);self.schedule()
    def paintEvent(self,event):super().paintEvent(event);self.schedule()
    def visible_rows(self):
        width=self.viewport().width();height=self.viewport().height();cell=self.gridSize();found=set()
        xs=list(range(cell.width()//2,width,cell.width()))+[1,max(1,width-2)]
        ys=list(range(0,height,max(1,cell.height()//2)))+[max(0,height-2)]
        for y in ys:
            for x in xs:
                index=self.indexAt(QPoint(x,y))
                if index.isValid():found.add(index.row())
        columns=max(1,width//cell.width());total=self.gallery_model.rowCount()
        return sorted({neighbor for i in found for neighbor in (i-columns,i,i+columns) if 0<=neighbor<total})

    def load_visible(self):
        if self.loading or not self.isVisible():return
        model=self.gallery_model;generation=model.generation
        needed=[i for i in self.visible_rows() if not model.entries[i].directory and model.key(model.entries[i]) not in model.cache][:8]
        if not needed:return
        self.loading=True;entries=[model.entries[i] for i in needed]
        def work(job):
            from .file_library import thumbnail
            return [thumbnail(entry.path,432,244) for entry in entries]
        def done(images):
            if not isValid(self):return
            self.loading=False
            if generation==model.generation:
                for i,entry,image in zip(needed,entries,images):
                    model.cache[model.key(entry)]=image
                    model.dataChanged.emit(model.index(i),model.index(i))
                capacity=max(96,len(self.visible_rows())+8)
                while len(model.cache)>capacity:model.cache.popitem(last=False)
            self.schedule()
        def failed(error):done([None]*len(entries))
        self.browser.owner.tasks.submit(work,done,failed)

    def open_index(self,index):
        entry=index.data(Qt.ItemDataRole.UserRole)
        if not entry:return
        if entry.directory:self.browser.enter(entry.path)
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.path)))
    def context(self,point):
        index=self.indexAt(point)
        if not index.isValid():return
        self.setCurrentIndex(index);entry=index.data(Qt.ItemDataRole.UserRole);menu=ActionMenu(self)
        menu.addAction('打开文件夹' if entry.directory else '查看原图',lambda:self.open_index(index))
        menu.addAction('打开所在目录',lambda:self.browser.owner.open_folder(entry.path.parent))
        menu.addAction('重命名',lambda:self.browser.rename(entry.path))
        menu.addAction('移入恢复区',lambda:self.browser.remove(entry.path));menu.exec(self.viewport().mapToGlobal(point))
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Delete and self.currentIndex().isValid():
            self.browser.remove(self.currentIndex().data(Qt.ItemDataRole.UserRole).path);return
        super().keyPressEvent(event)
