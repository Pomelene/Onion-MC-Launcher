"""Instance selection and management keep every action bound to one instance."""
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QWidget,QDialog,QLineEdit,QTreeWidget,QTreeWidgetItem,QStackedWidget,QFormLayout,QMessageBox
from .widgets import Page,Card,column,row,label,button,clear


class InstancePicker(QDialog):
    def __init__(self,launcher):
        super().__init__(launcher,Qt.WindowType.Popup);self.launcher=launcher;self.resize(380,390)
        body=column(self,12,10);self.query=QLineEdit();self.query.setPlaceholderText('搜索实例名称、版本或分组');body.addWidget(self.query)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setRootIsDecorated(False);self.tree.setColumnCount(2);self.tree.setColumnWidth(0,210);self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);body.addWidget(self.tree,1)
        body.addWidget(button('打开完整实例列表',self.open_list,'soft','grid'))
        self.query.textChanged.connect(self.filter);self.tree.itemClicked.connect(self.choose)
        self.query.returnPressed.connect(lambda:self.choose(self.tree.currentItem()) if self.tree.currentItem() else None);self.filter()

    def filter(self):
        w=self.launcher;query=self.query.text().strip().lower();self.tree.clear()
        for vid in w.versions:
            if query not in (vid+' '+w.instances.display_name(vid)+' '+w.instances.get(vid).group).lower():continue
            item=QTreeWidgetItem([w.instances.display_name(vid),w.kinds.get(vid,'原版')]);item.setData(0,Qt.ItemDataRole.UserRole,vid);item.setToolTip(0,vid);self.tree.addTopLevelItem(item)
            if vid==w.selected_version:self.tree.setCurrentItem(item)

    def choose(self,item,column=0):
        if item and self.launcher.set_selected(item.data(0,Qt.ItemDataRole.UserRole)):self.accept()

    def open_list(self):self.accept();self.launcher.navigate('versions')

    def show_above(self,anchor):
        point=anchor.mapToGlobal(QPoint(anchor.width()-self.width(),-self.height()-8))
        screen=anchor.screen().availableGeometry();self.move(max(screen.left(),min(point.x(),screen.right()-self.width())),max(screen.top(),point.y()))
        self.show();self.query.setFocus()


class InstanceWorkspace(QWidget):
    def __init__(self,launcher,vid):
        super().__init__();self.launcher=launcher;self.vid=vid;self.pages={};self.buttons={}
        body=column(self,12,0);self.stack=QStackedWidget();body.addWidget(self.stack,1)
        from .settings import SettingsEditor
        self.editor=SettingsEditor(launcher,vid,flat=True);self.pages['game']=self.editor;self.stack.addWidget(self.editor)

    def open_tab(self,key):
        w=self.launcher;w.instance_tab=key
        for name,item in self.buttons.items():item.setChecked(name==key)
        if key not in self.pages:
            self.pages[key]=Page();self.stack.addWidget(self.pages[key])
        self.stack.setCurrentWidget(self.pages[key])
        if key=='game':self.editor.refresh_inherited();return
        w.instance_content=self.pages[key]
        if key in ('mods','resourcepacks','shaderpacks'):w.build_mods(key)
        elif key=='worlds':w.build_worlds()
        elif key=='logs':w.build_logs()
        elif key=='info':self.build_info()
        elif key=='auto':self.build_auto()

    def build_auto(self):
        w=self.launcher;page=self.pages['auto'];clear(page.body)
        page.body.addWidget(label('游戏组件','eyebrow'))
        for title,detail in [('Minecraft',self.vid),('当前加载器',w.kinds.get(self.vid,'原版'))]:
            card=Card();line=row();line.addWidget(label(title),1);line.addWidget(label(detail,'muted'));card.body.addLayout(line);page.body.addWidget(card)
        page.body.addWidget(label('为此版本创建带加载器的新版本，已有实例文件保持原状。','muted',True))
        page.body.addWidget(button('选择并安装加载器',w.install_dialog,'soft','plus'))

    def build_info(self):
        w=self.launcher;page=self.pages['info'];clear(page.body);meta=w.instances.get(self.vid)
        card=Card('实例信息');fields={};form=QFormLayout()
        for key,title,value in [('name','显示名称',meta.name),('group','分组',meta.group),('notes','备注',meta.notes)]:
            edit=QLineEdit(value);edit.setPlaceholderText(self.vid if key=='name' else '可选');fields[key]=edit;form.addRow(title,edit)
        card.body.addLayout(form)
        def save():
            w.instances.update(self.vid,**{key:edit.text().strip() for key,edit in fields.items()});w.update_selection();w.reload_versions(refresh_page=False);w.status.setText('实例信息已保存')
        card.body.addWidget(button('保存实例信息',save,'primary'));page.body.addWidget(card)
        card=Card('维护与恢复','文件移除后进入恢复中心，可在原位置不存在时恢复。')
        for title,callback in [('校验游戏文件',lambda:w.verify_version(self.vid)),('导出整合包',lambda:w.export_modpack(self.vid)),('恢复中心',w.recovery),('移除当前实例',lambda:w.delete_version(self.vid))]:card.body.addWidget(button(title,callback,'soft'))
        page.body.addWidget(card)
