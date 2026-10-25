"""Select an explicit compatible catalog release inside the main window."""
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidgetItem,QWidget
from .widgets import column,row,label,button,ContentCheck
from ..catalog import pick_version,versions


class ProjectVersions(QDialog):
    def __init__(self,window,project_id,title,kind,game,loader,vid):
        super().__init__(window);self.launcher=window;self.project_id=project_id;self.kind=kind;self.game=game;self.loader=loader;self.vid=vid;self.entries=[];self.active=True
        from .browser import TITLES
        self.navigation_title='下载 / '+TITLES[kind]+' / 选择版本'
        self.setWindowTitle('选择版本 · '+title);body=column(self,24,12)
        body.addWidget(label(title,'heading',True))
        context=' · '.join(value for value in (window.instances.display_name(vid) if vid else '新建实例',game,loader) if value)
        body.addWidget(label(context,'muted',True))
        filter_bar=row();self.compatible=ContentCheck();self.compatible.setAccessibleName('仅显示兼容版本');self.compatible.setChecked(True);filter_bar.addWidget(self.compatible);filter_bar.addWidget(label('仅兼容版本','muted'));filter_bar.addStretch()
        self.refresh_button=button('',self.fetch,glyph='refresh');self.refresh_button.setToolTip('刷新版本');self.refresh_button.setAccessibleName('刷新版本');filter_bar.addWidget(self.refresh_button);body.addLayout(filter_bar)
        self.tree=QTreeWidget();self.tree.setColumnCount(1);self.tree.setHeaderHidden(True);body.addWidget(self.tree,1)
        actions=row();self.status=label('正在获取版本列表…','muted',True);actions.addWidget(self.status,1)
        self.install_button=button('安装',self.install,'primary','download');self.install_button.setEnabled(False);actions.addWidget(self.install_button);body.addLayout(actions)
        self.compatible.toggled.connect(self.render);self.tree.currentItemChanged.connect(lambda *_:self.update_selection());self.tree.itemDoubleClicked.connect(lambda *_:self.install())
        self.finished.connect(lambda _:setattr(self,'active',False));self.loading=False;QTimer.singleShot(0,self.fetch)

    def fetch(self):
        if not self.active or self.loading:return
        self.loading=True;self.refresh_button.setEnabled(False);self.update_selection();self.status.setText('正在获取版本列表…')
        def done(entries):
            self.loading=False
            if not self.active:return
            self.refresh_button.setEnabled(True)
            self.entries=sorted(entries,key=lambda v:v.get('date_published',''),reverse=True);self.render()
        def failed(error):
            self.loading=False
            if self.active:
                self.refresh_button.setEnabled(True);self.update_selection();self.status.setText('获取失败：'+str(error)+'；可点击刷新重试。')
        self.launcher.tasks.submit(lambda job:versions(self.launcher.repo.downloader,self.project_id),done,failed)

    def render(self,*args):
        current=self.tree.currentItem();selected_id=current.data(0,Qt.ItemDataRole.UserRole) if current else None
        self.tree.clear();first=None;selected=None
        for version in self.entries:
            compatible=bool(pick_version([version],self.game,self.loader))
            if self.compatible.isChecked() and not compatible:continue
            files=version.get('files') or [];primary=next((f for f in files if f.get('primary')),files[0] if files else {})
            channel={'release':'正式版','beta':'测试版','alpha':'预览版'}.get(version.get('version_type'),'')
            context=', '.join(version.get('game_versions') or [])+' / '+', '.join(version.get('loaders') or [])
            detail=' · '.join(v for v in (channel,version.get('date_published','')[:10],context.strip(' /') if not self.compatible.isChecked() else '') if v)
            if not compatible:detail+=' · 不兼容'
            item=QTreeWidgetItem([version.get('version_number') or version.get('name') or '']);item.setData(0,DETAIL_ROLE,detail)
            item.setData(0,Qt.ItemDataRole.UserRole,version.get('id'));item.setData(0,Qt.ItemDataRole.UserRole+1,compatible and bool(files))
            item.setToolTip(0,item.text(0)+'\n'+detail+'\n'+context+'\n'+primary.get('filename',''))
            if not compatible:item.setToolTip(0,'不匹配当前目标，无法安装到此实例')
            self.tree.addTopLevelItem(item)
            if version.get('id')==selected_id:selected=item
            if first is None and compatible and files:first=item
        if selected is not None or first is not None:self.tree.setCurrentItem(selected if selected is not None else first)
        count=self.tree.topLevelItemCount()
        self.status.setText(f'{count} 个版本' if count else '没有兼容版本');self.update_selection()

    def update_selection(self):
        item=self.tree.currentItem();self.install_button.setEnabled(bool(not self.loading and item and item.data(0,Qt.ItemDataRole.UserRole+1)))

    def install(self):
        if self.loading or not self.active:return
        item=self.tree.currentItem()
        if not item or not item.data(0,Qt.ItemDataRole.UserRole+1):return
        if self.launcher.install_project(self.project_id,self.kind,self.game,self.loader,version_id=self.vid,release_id=item.data(0,Qt.ItemDataRole.UserRole)):self.accept()
