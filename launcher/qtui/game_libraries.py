"""Folder rail for the instance library, with native directory selection."""
from pathlib import Path
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QWidget,QFileDialog,QInputDialog,QScrollArea
from .widgets import column,row,label,button,NavigationItem,control_accent
from .theme import config_for,surface_opacity,corner
from .choices import ActionMenu
from ..game_libraries import GameLibraries
from ..storage import directory_key


class LibraryItem(NavigationItem):
    def paintEvent(self,event):
        if self.isChecked():
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color=QColor(control_accent(self));color.setAlpha(round(38*surface_opacity(config_for(self))))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(color)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2,3,-2,-3),corner(self,8),corner(self,8));painter.end()
        super().paintEvent(event)


class LibraryRail(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.setFixedWidth(220);body=column(self,12,6)
        title=row();title.addWidget(label('游戏文件夹','heading'),1)
        add=button('',self.add,glyph='plus');add.setToolTip('添加游戏文件夹');add.setAccessibleName('添加游戏文件夹');title.addWidget(add);body.addLayout(title)
        scroll=QScrollArea();scroll.setFrameShape(scroll.Shape.NoFrame);scroll.setWidgetResizable(True);body.addWidget(scroll,1)
        items=QWidget();listing=column(items,0,4);scroll.setWidget(items)
        current=directory_key(window.repo.game_dir);self.buttons={}
        for entry in window.game_libraries.entries():
            path=entry['path'];available=Path(path).is_dir();key=directory_key(path)
            item=LibraryItem(GameLibraries.title(entry),'folder',lambda p=path:window.switch_game_library(p),str(path) if available else '暂时不可用')
            item.setChecked(key==current);item.setToolTip(str(path));item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            item.customContextMenuRequested.connect(lambda point,p=path,w=item:self.context(w,point,p))
            listing.addWidget(item);self.buttons[key]=item
        listing.addStretch();body.addWidget(button('全部实例总览',window.open_instance_overview,'soft','grid'));body.addWidget(button('添加游戏文件夹',self.add,glyph='plus'))
        body.addWidget(label('右键可重命名或移出列表','muted',True))

    def add(self):
        path=QFileDialog.getExistingDirectory(self,'添加游戏文件夹',str(self.window.repo.game_dir))
        if path:self.window.add_game_library(path)

    def context(self,widget,point,path):
        menu=ActionMenu(self);menu.addAction('打开文件夹',lambda:self.window.open_folder(Path(path)))
        def rename():
            name,ok=QInputDialog.getText(self,'文件夹名称','列表中的显示名称（不会修改磁盘目录名）')
            if ok:self.window.game_libraries.rename(path,name);self.window.build_sidebar('versions')
        menu.addAction('重命名',rename)
        action=menu.addAction('从列表移除',lambda:self.window.remove_game_library(path))
        action.setEnabled(directory_key(path)!=directory_key(self.window.repo.game_dir))
        menu.exec(widget.mapToGlobal(point))
