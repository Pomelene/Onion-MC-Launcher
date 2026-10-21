"""Select an explicit compatible catalog release inside the main window."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidget,QTreeWidgetItem,QCheckBox
from .widgets import column,row,label,button,ContentCheck
from ..catalog import pick_version,versions


class ProjectVersions(QDialog):
    def __init__(self,window,project_id,title,kind,game,loader,vid):
        super().__init__(window);self.launcher=window;self.project_id=project_id;self.kind=kind;self.game=game;self.loader=loader;self.vid=vid;self.entries=[];self.active=True
        self.setWindowTitle('选择版本 · '+title);body=column(self,24,12)
        body.addWidget(label(title,'heading'));body.addWidget(label(f'目标：{window.instances.display_name(vid) if vid else "新实例"} · {game or "不限游戏版本"} · {loader or "不限加载器"}','muted'))
        filter_bar=row();self.compatible=ContentCheck();self.compatible.setAccessibleName('仅显示兼容版本');self.compatible.setChecked(True);filter_bar.addWidget(self.compatible);filter_bar.addWidget(label('仅显示匹配当前游戏版本与加载器的文件'));filter_bar.addStretch();body.addLayout(filter_bar)
        self.tree=QTreeWidget();self.tree.setRootIsDecorated(False);self.tree.setHeaderLabels(['版本','发布渠道','游戏版本 / 加载器','发布时间','文件'])
        for i,width in enumerate((220,90,260,110)):self.tree.setColumnWidth(i,width)
        body.addWidget(self.tree,1);self.status=label('正在获取版本列表…','muted',True);body.addWidget(self.status)
        actions=row();actions.addWidget(button('刷新',self.fetch,glyph='history'));actions.addStretch();actions.addWidget(button('返回',self.reject));self.install_button=button('安装选中版本',self.install,'primary','download');self.install_button.setEnabled(False);actions.addWidget(self.install_button);body.addLayout(actions)
        self.compatible.toggled.connect(self.render);self.tree.currentItemChanged.connect(lambda *_:self.update_selection());self.tree.itemDoubleClicked.connect(lambda *_:self.install())
        self.finished.connect(lambda _:setattr(self,'active',False));self.loading=False;QTimer.singleShot(0,self.fetch)

    def fetch(self):
        if self.loading:return
        self.loading=True;self.status.setText('正在获取版本列表…')
        def done(entries):
            self.loading=False
            if not self.active:return
            self.entries=sorted(entries,key=lambda v:v.get('date_published',''),reverse=True);self.render()
        def failed(error):
            self.loading=False
            if self.active:self.status.setText('获取失败：'+str(error))
        self.launcher.tasks.submit(lambda job:versions(self.launcher.repo.downloader,self.project_id),done,failed)

    def render(self,*args):
        self.tree.clear();first=None
        for version in self.entries:
            compatible=bool(pick_version([version],self.game,self.loader))
            if self.compatible.isChecked() and not compatible:continue
            files=version.get('files') or [];primary=next((f for f in files if f.get('primary')),files[0] if files else {})
            item=QTreeWidgetItem([version.get('version_number') or version.get('name') or '',{'release':'正式版','beta':'测试版','alpha':'预览版'}.get(version.get('version_type'),''),', '.join(version.get('game_versions') or [])+' / '+', '.join(version.get('loaders') or []),version.get('date_published','')[:10],primary.get('filename','')])
            item.setData(0,Qt.ItemDataRole.UserRole,version.get('id'));item.setData(0,Qt.ItemDataRole.UserRole+1,compatible and bool(files))
            if not compatible:item.setToolTip(0,'不匹配当前目标，无法安装到此实例')
            self.tree.addTopLevelItem(item)
            if first is None and compatible and files:first=item
        if first:self.tree.setCurrentItem(first)
        self.status.setText(f'显示 {self.tree.topLevelItemCount()} / {len(self.entries)} 个版本；安装前会再次核对兼容性。');self.update_selection()

    def update_selection(self):
        item=self.tree.currentItem();self.install_button.setEnabled(bool(item and item.data(0,Qt.ItemDataRole.UserRole+1)))

    def install(self):
        item=self.tree.currentItem()
        if not item or not item.data(0,Qt.ItemDataRole.UserRole+1):return
        if self.launcher.install_project(self.project_id,self.kind,self.game,self.loader,version_id=self.vid,release_id=item.data(0,Qt.ItemDataRole.UserRole)):self.accept()
