"""Instance schematic browser and continuous screenshot gallery."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QImageReader, QPixmap, QDesktopServices
from PySide6.QtWidgets import QWidget,QLineEdit,QFileDialog,QInputDialog,QMessageBox,QLabel
from shiboken6 import isValid
from .choices import ChoiceComboBox
from .widgets import row,column,label,button,ContentRow,Empty,clear
from ..file_library import scan_library,import_files,rename_entry,remove_entry,checked_folder
from ..safety import contained,component,restore_recycled


def thumbnail(path, width=200, height=120):
    reader=QImageReader(str(path));size=reader.size()
    if not size.isValid() or size.width()*size.height()>64_000_000:return None
    reader.setScaledSize(size.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


class InstanceFiles(QWidget):
    def __init__(self, launcher, vid, pictures=False):
        super().__init__();self.owner=launcher;self.vid=vid;self.pictures=pictures
        self.root=launcher.repo.run_dir(vid)/('screenshots' if pictures else 'schematics')
        self.relative='';self.entries=[];self.page_index=0;self.generation=0;self.last_removed=None
        body=column(self,0,12);toolbar=row(spacing=8)
        self.up=button('',self.parent_folder,glyph='back');self.up.setToolTip('上一级');toolbar.addWidget(self.up)
        self.location=QLineEdit();self.location.setReadOnly(True);toolbar.addWidget(self.location,1)
        toolbar.addWidget(button('刷新',self.reload,glyph='refresh'))
        toolbar.addWidget(button('打开目录',self.open_folder,glyph='folder'))
        if not pictures:
            toolbar.addWidget(button('新建文件夹',self.new_folder,glyph='plus'))
            toolbar.addWidget(button('导入原理图',self.import_schematics,'soft','plus'))
        body.addLayout(toolbar)
        controls=row();self.query=QLineEdit();self.query.setPlaceholderText('搜索当前目录');self.query.setClearButtonEnabled(True);controls.addWidget(self.query,1)
        self.undo=button('撤销移除',self.undo_remove);self.undo.setEnabled(False);controls.addWidget(self.undo)
        self.count=label('','muted');controls.addWidget(self.count)
        self.per_page=None
        if not pictures:
            self.per_page=ChoiceComboBox()
            for number in (12,24,48,96):self.per_page.addItem(f'每页 {number} 项',number)
            self.per_page.setCurrentIndex(max(0,self.per_page.findData(launcher.config_obj.get('schematic_page_size') or 24)))
            controls.addWidget(self.per_page)
        body.addLayout(controls)
        if pictures:
            from .screenshot_gallery import ScreenshotGallery
            self.gallery=ScreenshotGallery(self);body.addWidget(self.gallery,1)
            self.query.textChanged.connect(self.filter);self.reload();return
        self.results=QWidget();self.list=column(self.results,0,0);body.addWidget(self.results)
        footer=row();footer.addStretch()
        self.previous=button('上一页',lambda:self.turn(-1));self.next=button('下一页',lambda:self.turn(1))
        footer.addWidget(self.previous);self.position=label('','muted');footer.addWidget(self.position);footer.addWidget(self.next);body.insertLayout(2,footer);body.addStretch()
        self.query.textChanged.connect(self.filter)
        def resize_page():
            launcher.config_obj.set('schematic_page_size',self.per_page.currentData());self.filter()
        self.per_page.currentIndexChanged.connect(resize_page);self.reload()

    def open_folder(self):
        try:
            folder=checked_folder(self.root,self.relative)
            self.owner.repo.assert_writable(folder);folder.mkdir(parents=True,exist_ok=True);self.owner.open_folder(folder)
        except Exception as error:self.owner.error(str(error))

    def parent_folder(self):
        self.relative=str(Path(self.relative).parent) if self.relative else ''
        if self.relative=='.':self.relative=''
        self.reload()

    def enter(self,path):
        self.relative=str(contained(path,self.root).relative_to(self.root));self.query.clear();self.reload()

    def reload(self):
        self.generation+=1;generation=self.generation;relative=self.relative
        self.location.setText(('截图' if self.pictures else '原理图')+' / '+relative.replace('\\','/'))
        self.location.setToolTip(str(self.root/relative));self.up.setEnabled(bool(relative));self.count.setText('正在读取…')
        def done(entries):
            if not isValid(self) or generation!=self.generation:return
            self.entries=entries;self.filter()
        self.owner.tasks.submit(lambda job:scan_library(self.root,relative,pictures=self.pictures),done,
            lambda error:self.owner.error(str(error)) if isValid(self) and generation==self.generation else None)

    def filter(self):self.page_index=0;self.render()

    def turn(self,step):self.page_index+=step;self.render()

    def render(self):
        self.generation+=1;generation=self.generation
        text=self.query.text().strip().casefold();entries=[item for item in self.entries if text in (item.path.name+' '+item.detail).casefold()]
        if self.pictures:
            count=sum(not item.directory for item in entries);self.count.setText(f'{count} 张截图')
            self.gallery.replace(entries);return
        clear(self.list)
        size=self.per_page.currentData();pages=max(1,(len(entries)+size-1)//size);self.page_index=max(0,min(self.page_index,pages-1))
        self.count.setText(f'{len(entries)} 项');self.position.setText(f'{self.page_index+1} / {pages}')
        self.previous.setEnabled(self.page_index>0);self.next.setEnabled(self.page_index+1<pages)
        if not entries:self.list.addWidget(Empty('这里还没有截图' if self.pictures else '这里还没有原理图','','grid' if self.pictures else 'schematic'));return
        thumbs=[]
        for entry in entries[self.page_index*size:(self.page_index+1)*size]:
            detail='文件夹' if entry.directory else ' · '.join(v for v in (entry.detail,datetime.fromtimestamp(entry.modified).strftime('%Y-%m-%d %H:%M'),f'{entry.size/1024:.1f} KiB') if v)
            item=ContentRow(entry.path.name,detail,'folder' if entry.directory else 'image' if self.pictures else 'schematic')
            if self.pictures and not entry.directory:
                item.setFixedHeight(104);item.image.setFixedSize(136,84);item.image.setAlignment(Qt.AlignmentFlag.AlignCenter);thumbs.append((item,entry.path))
            item.action('打开文件夹' if entry.directory else '查看截图' if self.pictures else '打开所在目录',
                lambda e=entry:self.enter(e.path) if e.directory else QDesktopServices.openUrl(QUrl.fromLocalFile(str(e.path))) if self.pictures else self.owner.open_folder(e.path.parent),'folder' if entry.directory else 'image' if self.pictures else 'folder')
            item.action('重命名',lambda e=entry:self.rename(e.path),'edit')
            item.action('移入恢复区',lambda e=entry:self.remove(e.path),'trash');self.list.addWidget(item)
        if thumbs:
            def ready(images):
                if not isValid(self) or generation!=self.generation:return
                for (widget,_),image in zip(thumbs,images):
                    if isValid(widget) and image is not None and not image.isNull():
                        widget.image.setPixmap(QPixmap.fromImage(image));widget.has_artwork=True
            self.owner.tasks.submit(lambda job:[thumbnail(path,272,168) for _,path in thumbs],ready,lambda error:None)

    def mutate(self,function,completed=None):
        if getattr(self,'editing',False):return
        self.editing=True;self.setEnabled(False)
        def work(job):
            self.owner.repo.assert_idle(self.vid);self.owner.repo.assert_writable(self.root)
            return function()
        def done(value):
            if not isValid(self):return
            self.editing=False;self.setEnabled(True)
            if completed:completed(value)
            self.reload()
        def failed(error):
            if not isValid(self):return
            self.editing=False;self.setEnabled(True);self.reload();self.owner.error(str(error))
        self.owner.tasks.submit(work,done,failed)

    def import_schematics(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入原理图','','原理图 (*.litematic *.schem *.schematic *.nbt)')
        if paths:self.mutate(lambda:import_files(self.root,self.relative,paths))

    def new_folder(self):
        name,ok=QInputDialog.getText(self,'新建文件夹','文件夹名称')
        if ok:self.mutate(lambda:contained(checked_folder(self.root,self.relative)/component(name),self.root).mkdir(parents=True,exist_ok=False))

    def rename(self,path):
        name,ok=QInputDialog.getText(self,'重命名','名称',text=path.name)
        if ok:self.mutate(lambda:rename_entry(self.root,path,name))

    def remove(self,path):
        if QMessageBox.question(self,'移入恢复区',f'将“{path.name}”移入恢复区？')!=QMessageBox.StandardButton.Yes:return
        def completed(stored):self.last_removed=(stored,path.parent);self.undo.setEnabled(True)
        self.mutate(lambda:remove_entry(self.root,path),completed)

    def undo_remove(self):
        if not self.last_removed:return
        stored,parent=self.last_removed
        def perform():contained(stored,self.root);return restore_recycled(stored,parent)
        def completed(value):self.last_removed=None;self.undo.setEnabled(False)
        self.mutate(perform,completed)
