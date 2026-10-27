"""Embedded workshop: skin wardrobe and local biome/structure map."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QImageReader,QPixmap
from PySide6.QtWidgets import QWidget,QStackedWidget,QLineEdit,QFileDialog,QSplitter,QInputDialog,QMessageBox,QCheckBox
from shiboken6 import isValid
from .widgets import Page,Card,ContentRow,Empty,column,row,label,button,clear,favorite_button,menu_button
from .choices import ChoiceComboBox
from .skin_preview import SkinPreview
from ..skins import SkinLibrary,upload_skin,skin_bytes,cape_profile,sync_cape,texture_bytes
from .seed_map import SeedMap


class Wardrobe(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.library=SkinLibrary(owner.root);self.path=None;self.uploading=False
        self.cape_account=None;self.capes={};self.cape_busy=False;self.cape_generation=0;self.official_skin=None
        body=column(self,0,14);toolbar=row()
        self.query=QLineEdit();self.query.setPlaceholderText('搜索皮肤');self.query.setClearButtonEnabled(True);self.query.textChanged.connect(self.refresh);toolbar.addWidget(self.query,1)
        self.favorites_only=ChoiceComboBox();self.favorites_only.addItems(['全部皮肤','仅收藏']);self.favorites_only.currentIndexChanged.connect(self.refresh);toolbar.addWidget(self.favorites_only)
        toolbar.addWidget(button('导入皮肤',self.import_skin,'soft','plus'));body.addLayout(toolbar)
        self.skin_count=label('','muted');self.skin_count.hide()
        split=QSplitter();body.addWidget(split,1)
        left=Page();left.setMinimumWidth(240);self.list=left.body;split.addWidget(left)
        right=QWidget();detail=column(right,24,14);self.preview=SkinPreview();detail.addWidget(self.preview,1)
        self.filename=label('选择皮肤','heading',True);detail.addWidget(self.filename)
        self.model=ChoiceComboBox();self.model.addItem('经典模型 · 4 像素手臂','classic');self.model.addItem('纤细模型 · 3 像素手臂','slim');detail.addWidget(self.model)
        self.account=label('','muted');detail.addWidget(self.account)
        self.render_cape=QCheckBox('预览时渲染披风');self.render_cape.setChecked(True);self.render_cape.toggled.connect(self.toggle_cape_preview);detail.addWidget(self.render_cape)
        cape_row=row();self.cape_choice=ChoiceComboBox();self.cape_choice.addItem('无披风',None);cape_row.addWidget(self.cape_choice,1)
        self.cape_apply=button('应用披风',self.apply_cape,'soft');cape_row.addWidget(self.cape_apply)
        self.cape_reload=button('刷新披风',self.load_capes,'soft','refresh');cape_row.addWidget(self.cape_reload);detail.addLayout(cape_row)
        self.cape_choice.currentIndexChanged.connect(self.preview_cape)
        actions=row();self.apply=button('应用到离线账户',self.apply_local,'primary','skin');actions.addWidget(self.apply)
        self.upload=button('上传并同步正版皮肤',self.upload_current,'primary','upload');actions.addWidget(self.upload);detail.addLayout(actions)
        self.status=label('','muted',True);detail.addWidget(self.status);split.addWidget(right);split.setSizes([400,560])
        self.reset=button('恢复离线默认皮肤',self.reset_local);detail.addWidget(self.reset)
        self.model.currentIndexChanged.connect(self.update_preview);self.refresh()

    def refresh(self):
        clear(self.list);account=self.owner.accounts.current()
        self.account.setText(account.username if account else '请先添加账户')
        online=bool(account and account.type=='microsoft')
        for control in (self.cape_choice,self.cape_apply,self.cape_reload):control.setVisible(online)
        identity=account.uuid if online else None
        if identity!=self.cape_account:
            self.cape_account=identity;self.cape_generation+=1;self.capes={};self.official_skin=None;self.preview.cape=QImage();self.cape_busy=False
            self.cape_choice.blockSignals(True);self.cape_choice.clear();self.cape_choice.addItem('无披风',None);self.cape_choice.blockSignals(False)
            if identity:self.load_capes()
        self.upload.setVisible(bool(account and account.type=='microsoft'))
        self.apply.setVisible(not account or account.type=='offline')
        self.reset.setVisible(bool(account and account.type=='offline'))
        self.apply.setEnabled(bool(account and account.type=='offline' and self.path))
        self.upload.setEnabled(bool(account and account.type=='microsoft' and self.path and not self.uploading))
        try:
            files=self.library.files();favorite_states={p:self.library.is_favorite(p) for p in files}
            total=len(files)
            files.sort(key=lambda p:(not favorite_states[p],p.name.casefold()))
            if self.favorites_only.currentIndex():files=[p for p in files if favorite_states[p]]
            query=self.query.text().strip().casefold()
            if query:files=[p for p in files if query in self.display_name(p).casefold() or query in p.name.casefold()]
            self.skin_count.setText(f'{len(files)} / {total}')
        except Exception as error:self.status.setText(str(error));return
        selected=self.library.selected(account.uuid) if account else None
        if not files:
            self.list.addWidget(Empty('尚无收藏' if self.favorites_only.currentIndex() else '导入你的第一张皮肤','支持经典和纤细模型的 PNG 皮肤','skin'))
            self.path=None;self.apply.setEnabled(False);self.upload.setEnabled(False);self.preview.image=self.official_skin or QImage();self.preview.update();self.filename.setText('选择皮肤');return
        for path in files:
            active=bool(selected and path==selected[0]);item=ContentRow(self.display_name(path),('当前账户使用中' if active else ''),'skin')
            try:image=QImage.fromData(skin_bytes(path))
            except (OSError,ValueError):image=QImage()
            if not image.isNull():item.image.setPixmap(QPixmap.fromImage(image.copy(8,8,8,8).scaled(32,32)));item.has_artwork=True
            item.mousePressEvent=lambda event,p=path:self.choose(p)
            item.line.addWidget(favorite_button(favorite_states[path],lambda checked=False,p=path:self.toggle_favorite(p)))
            item.line.addWidget(menu_button(lambda p=path:[('重命名',lambda:self.rename_skin(p)),('移入恢复区',lambda:self.remove_skin(p))]));self.list.addWidget(item)
        if not self.path or self.path not in files:
            if selected and selected[0] in files:self.model.setCurrentIndex(max(0,self.model.findData(selected[1])))
            self.choose(selected[0] if selected and selected[0] in files else files[0])
        else:self.choose(self.path)

    @staticmethod
    def display_name(path):
        import re
        return re.sub(r'-[a-f0-9]{10}$','',path.stem)

    def toggle_favorite(self,path):
        try:self.library.set_favorite(path,not self.library.is_favorite(path));self.refresh()
        except Exception as error:self.owner.error(str(error))

    def choose(self,path):
        self.path=path;self.filename.setText(self.display_name(path));self.filename.setToolTip(str(path));self.update_preview()
        account=self.owner.accounts.current();self.apply.setEnabled(bool(account and account.type=='offline'))
        self.upload.setEnabled(bool(account and account.type=='microsoft' and not self.uploading))

    def update_preview(self):
        if self.path:
            try:self.preview.load(self.path,self.model.currentData()=='slim')
            except Exception as error:self.status.setText(str(error))

    def preview_cape(self):
        item=self.capes.get(self.cape_choice.currentData())
        self.preview.cape=QImage.fromData(item['texture']) if item and item.get('texture') else QImage()
        if not self.preview.cape.isNull() and self.preview.cape.width()!=64:self.preview.cape=self.preview.cape.scaled(64,32,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
        self.preview._textures.clear();self.preview.update()

    def toggle_cape_preview(self,enabled):
        self.preview.show_cape=enabled;self.preview.update()

    def load_capes(self):
        account=self.owner.accounts.current()
        if not account or account.type!='microsoft' or self.cape_busy:return
        self.cape_generation+=1;generation=self.cape_generation;identity=account.uuid;self.cape_busy=True
        self.cape_reload.setEnabled(False);self.cape_apply.setEnabled(False);self.status.setText('正在同步披风…')
        def texture(url):
            # Mojang profile URLs may use HTTP; upgrade only its texture host.
            if isinstance(url,str) and url.startswith('http://textures.minecraft.net/'):url='https://'+url[7:]
            try:return texture_bytes(url)
            except Exception:return None
        def work(job):
            fresh=self.owner.accounts.ensure_fresh(account);profile=cape_profile(fresh);capes=[]
            from concurrent.futures import ThreadPoolExecutor
            for item in profile.get('capes',[])[:64]:
                if isinstance(item,dict) and isinstance(item.get('id'),str):
                    capes.append({'id':item['id'],'name':str(item.get('alias') or '披风')[:80], 'active':item.get('state')=='ACTIVE','url':item.get('url')})
            skins=profile.get('skins',[]);active=next((s for s in skins if isinstance(s,dict) and s.get('state')=='ACTIVE'),{}) if isinstance(skins,list) else {}
            with ThreadPoolExecutor(max_workers=6) as pool:
                images=list(pool.map(texture,[item['url'] for item in capes]+[active.get('url')]))
            for item,data in zip(capes,images):item['texture']=data
            return capes,images[-1],active.get('variant')=='SLIM'
        def done(result):
            if not isValid(self) or generation!=self.cape_generation or identity!=self.cape_account:return
            self.cape_busy=False;self.cape_reload.setEnabled(True);self.cape_apply.setEnabled(True)
            capes,skin,slim=result;self.capes={item['id']:item for item in capes}
            self.cape_choice.blockSignals(True);self.cape_choice.clear();self.cape_choice.addItem('无披风',None);selected=0
            for item in capes:
                self.cape_choice.addItem(item['name'],item['id'])
                if item['active']:selected=self.cape_choice.count()-1
            self.cape_choice.setCurrentIndex(selected);self.cape_choice.blockSignals(False)
            image=QImage.fromData(skin or b'')
            if not image.isNull() and image.width()==64 and image.height() in (32,64):
                self.official_skin=image
                if not self.path:self.preview.image=image;self.preview.slim=slim
            self.preview_cape();self.status.setText('部分纹理加载失败，可点击刷新重试' if any(not item['texture'] for item in capes) else '')
        def failed(error):
            if isValid(self) and generation==self.cape_generation and identity==self.cape_account:
                self.cape_busy=False;self.cape_reload.setEnabled(True);self.cape_apply.setEnabled(False);self.status.setText(str(error))
        self.owner.tasks.submit(work,done,failed)

    def apply_cape(self):
        account=self.owner.accounts.current()
        if not account or account.type!='microsoft' or self.cape_busy:return
        cape_id=self.cape_choice.currentData();identity=account.uuid;generation=self.cape_generation;self.cape_busy=True
        self.cape_apply.setEnabled(False);self.cape_reload.setEnabled(False);self.status.setText('正在应用披风…')
        def work(job):return sync_cape(self.owner.accounts.ensure_fresh(account),cape_id)
        def done(result):
            if isValid(self) and generation==self.cape_generation and identity==self.cape_account:
                self.cape_busy=False;self.cape_reload.setEnabled(True);self.cape_apply.setEnabled(True);self.status.setText('披风已同步')
        def failed(error):
            if isValid(self) and generation==self.cape_generation and identity==self.cape_account:
                self.cape_busy=False;self.cape_reload.setEnabled(True);self.cape_apply.setEnabled(True);self.status.setText(str(error))
        self.owner.tasks.submit(work,done,failed)

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
            self.views[key]=Wardrobe(self.owner) if key=='skins' else SeedMap(self.owner)
            self.stack.addWidget(self.views[key])
        self.stack.setCurrentWidget(self.views[key])
        if key=='skins':self.views[key].refresh()
        return True
