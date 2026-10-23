"""Embedded workshop: skin wardrobe and local biome/structure map."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QImageReader,QPixmap
from PySide6.QtWidgets import QWidget,QStackedWidget,QLineEdit,QFileDialog,QSplitter,QInputDialog,QMessageBox
from shiboken6 import isValid
from .widgets import Page,Card,ContentRow,Empty,column,row,label,button,clear
from .choices import ChoiceComboBox
from .skin_preview import SkinPreview
from ..skins import SkinLibrary,upload_skin,skin_bytes
from .seed_map import SeedMap


class Wardrobe(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.library=SkinLibrary(owner.root);self.path=None;self.uploading=False
        body=column(self,0,14);toolbar=row();toolbar.addWidget(label('皮肤库','heading'),1)
        toolbar.addWidget(button('导入皮肤',self.import_skin,'soft','plus'));body.addLayout(toolbar)
        split=QSplitter();body.addWidget(split,1)
        left=Page();left.setMinimumWidth(240);self.list=left.body;split.addWidget(left)
        right=QWidget();detail=column(right,24,14);self.preview=SkinPreview();detail.addWidget(self.preview,1)
        self.filename=label('选择皮肤','heading',True);detail.addWidget(self.filename)
        self.model=ChoiceComboBox();self.model.addItem('经典模型 · 4 像素手臂','classic');self.model.addItem('纤细模型 · 3 像素手臂','slim');detail.addWidget(self.model)
        self.account=label('','muted');detail.addWidget(self.account)
        actions=row();self.apply=button('应用到离线账户',self.apply_local,'primary','skin');actions.addWidget(self.apply)
        self.upload=button('上传并同步正版皮肤',self.upload_current,'primary','upload');actions.addWidget(self.upload);detail.addLayout(actions)
        self.status=label('','muted',True);detail.addWidget(self.status);split.addWidget(right);split.setSizes([400,560])
        self.reset=button('恢复离线默认皮肤',self.reset_local);detail.addWidget(self.reset)
        self.model.currentIndexChanged.connect(self.update_preview);self.refresh()

    def refresh(self):
        clear(self.list);account=self.owner.accounts.current()
        self.account.setText(account.username if account else '请先添加账户')
        self.upload.setVisible(bool(account and account.type=='microsoft'))
        self.apply.setVisible(not account or account.type=='offline')
        self.reset.setVisible(bool(account and account.type=='offline'))
        self.apply.setEnabled(bool(account and account.type=='offline' and self.path))
        self.upload.setEnabled(bool(account and account.type=='microsoft' and self.path and not self.uploading))
        try:files=self.library.files()
        except Exception as error:self.status.setText(str(error));return
        selected=self.library.selected(account.uuid) if account else None
        if not files:self.list.addWidget(Empty('导入你的第一张皮肤','支持经典和纤细模型的 PNG 皮肤','skin'));return
        for path in files:
            active=bool(selected and path==selected[0]);item=ContentRow(self.display_name(path),('当前账户使用中' if active else ''),'skin')
            try:image=QImage.fromData(skin_bytes(path))
            except (OSError,ValueError):image=QImage()
            if not image.isNull():item.image.setPixmap(QPixmap.fromImage(image.copy(8,8,8,8).scaled(32,32)));item.has_artwork=True
            item.mouseDoubleClickEvent=lambda event,p=path:self.choose(p)
            item.action('预览',lambda p=path:self.choose(p),'skin')
            item.action('重命名',lambda p=path:self.rename_skin(p),'edit')
            item.action('移入恢复区',lambda p=path:self.remove_skin(p),'trash');self.list.addWidget(item)
        if not self.path or self.path not in files:
            if selected:self.model.setCurrentIndex(max(0,self.model.findData(selected[1])))
            self.choose(selected[0] if selected else files[0])
        else:self.choose(self.path)

    @staticmethod
    def display_name(path):
        import re
        return re.sub(r'-[a-f0-9]{10}$','',path.stem)

    def choose(self,path):
        self.path=path;self.filename.setText(self.display_name(path));self.filename.setToolTip(str(path));self.update_preview()
        account=self.owner.accounts.current();self.apply.setEnabled(bool(account and account.type=='offline'))
        self.upload.setEnabled(bool(account and account.type=='microsoft' and not self.uploading))

    def update_preview(self):
        if self.path:
            try:self.preview.load(self.path,self.model.currentData()=='slim')
            except Exception as error:self.status.setText(str(error))

    def import_skin(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入皮肤','','Minecraft 皮肤 (*.png)')
        try:
            for path in paths:
                image=QImage.fromData(skin_bytes(path))
                if image.isNull():raise ValueError('PNG 皮肤无法解码')
                self.path=self.library.import_skin(path)
            self.refresh();self.update_preview()
        except Exception as error:self.owner.error(str(error))

    def apply_local(self):
        account=self.owner.accounts.current()
        if not account or account.type!='offline' or not self.path:return
        try:
            self.library.select(account.uuid,self.path,self.model.currentData());self.refresh()
            self.status.setText('已保存，下次启动游戏生效。仅本地显示，不会上传。')
        except Exception as error:self.owner.error(str(error))

    def reset_local(self):
        account=self.owner.accounts.current()
        if account and account.type=='offline':
            try:self.library.reset(account.uuid);self.refresh();self.status.setText('下次启动将使用离线默认皮肤。')
            except Exception as error:self.owner.error(str(error))

    def rename_skin(self,path):
        name,ok=QInputDialog.getText(self,'重命名皮肤','文件名称',text=path.name)
        if not ok:return
        from ..file_library import rename_entry
        try:
            linked=[(account.uuid,item[1]) for account in self.owner.accounts.accounts if (item:=self.library.selected(account.uuid)) and item[0]==path]
            new=rename_entry(self.library.root,path,name)
            for uid,variant in linked:self.library.select(uid,new,variant)
            if self.path==path:self.path=new
            self.refresh()
        except Exception as error:self.owner.error(str(error))

    def remove_skin(self,path):
        if QMessageBox.question(self,'移入恢复区',f'移除“{path.stem}”？使用它的离线账户将恢复默认皮肤。')!=QMessageBox.StandardButton.Yes:return
        from ..file_library import remove_entry
        try:
            for account in self.owner.accounts.accounts:
                selected=self.library.selected(account.uuid)
                if selected and selected[0]==path:self.library.reset(account.uuid)
            remove_entry(self.library.root,path)
            if self.path==path:self.path=None;self.preview.image=QImage();self.preview.update()
            self.refresh()
        except Exception as error:self.owner.error(str(error))

    def upload_current(self):
        account=self.owner.accounts.current()
        if not account or account.type!='microsoft' or not self.path or self.uploading:return
        path=self.path;variant=self.model.currentData();self.uploading=True;self.upload.setEnabled(False)
        self.status.setText('正在上传…')
        def work(job):
            fresh=self.owner.accounts.ensure_fresh(account);upload_skin(fresh,path,variant)
            self.library.select(fresh.uuid,path,variant)
        def done(result):
            if isValid(self):self.uploading=False;self.refresh();self.status.setText('正版皮肤已上传。已运行的游戏可能需要重新进入。')
        def failed(error):
            if isValid(self):self.uploading=False;self.refresh();self.status.setText(str(error))
        self.owner.tasks.submit(work,done,failed)


class Workshop(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.views={};body=column(self,24,0);self.stack=QStackedWidget();body.addWidget(self.stack)
    def open_tab(self,key):
        if key not in self.views:
            self.views[key]=Wardrobe(self.owner) if key=='skins' else SeedMap(self.owner);self.stack.addWidget(self.views[key])
        self.stack.setCurrentWidget(self.views[key])
        if key=='skins':self.views[key].refresh()
