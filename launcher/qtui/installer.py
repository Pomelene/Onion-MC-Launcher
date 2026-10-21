"""Version-first installation dialog, using the existing installer services."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QLineEdit,QComboBox,QCheckBox,QTreeWidget,QTreeWidgetItem,QWidget
from .widgets import column,row,label,button,Card


class InstallDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.launcher=window;self.entries=[];self.loading=False;self.active=True
        self.setWindowTitle('安装 Minecraft');self.resize(940,670);self.setMinimumSize(820,570)
        body=column(self,26,18);body.addWidget(label('安装 Minecraft','title'));body.addWidget(label('选择游戏版本，再添加喜欢的模组加载器。','muted'))
        panels=row(spacing=20);body.addLayout(panels,1)
        left=QWidget();list_body=column(left,0,12);panels.addWidget(left,3)
        search=row();self.query=QLineEdit();self.query.setPlaceholderText('筛选版本，例如 1.21');search.addWidget(self.query,1)
        self.snapshots=QCheckBox('快照与旧版');search.addWidget(self.snapshots);list_body.addLayout(search)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['游戏版本','类型','发布时间']);self.tree.setRootIsDecorated(False);self.tree.setColumnWidth(0,150);self.tree.setColumnWidth(1,85);list_body.addWidget(self.tree,1)
        self.status=label('正在获取版本列表…','muted',True);list_body.addWidget(self.status)
        self.retry=button('刷新版本列表',self.fetch,glyph='history');list_body.addWidget(self.retry,alignment=Qt.AlignmentFlag.AlignLeft)
        options=Card('安装选项','原版与加载器将安装到当前游戏库。');options.setFixedWidth(290);panels.addWidget(options)
        options.body.addWidget(label('Minecraft 版本','heading'));self.version=QLineEdit();self.version.setPlaceholderText('从左侧选择，或输入版本号');options.body.addWidget(self.version)
        options.body.addWidget(label('模组加载器','heading'));self.loader=QComboBox()
        for title,key in [('原版 Minecraft','vanilla'),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt'),('OptiFine','optifine')]:self.loader.addItem(title,key)
        options.body.addWidget(self.loader)
        self.build=QLineEdit();self.build.setPlaceholderText('自动选择兼容版本');self.build.setEnabled(False);options.body.addWidget(label('加载器版本（可选）','muted'));options.body.addWidget(self.build)
        options.body.addWidget(label('Java 将根据游戏版本自动匹配。安装完成后可在实例设置中调整内存与窗口。','muted',True));options.body.addStretch()
        options.body.addWidget(label('下载位置','eyebrow'));options.body.addWidget(label(str(window.repo.game_dir),'muted',True))
        actions=row();actions.addStretch();actions.addWidget(button('取消',self.reject));self.install_button=button('开始安装',self.install,'primary','download');actions.addWidget(self.install_button);body.addLayout(actions)
        self.query.textChanged.connect(self.render_versions);self.snapshots.toggled.connect(self.render_versions)
        self.loader.currentIndexChanged.connect(lambda:self.build.setEnabled(self.loader.currentData()!='vanilla'))
        self.tree.currentItemChanged.connect(self.choose);self.tree.itemDoubleClicked.connect(lambda *_:self.install())
        self.finished.connect(lambda _:setattr(self,'active',False));QTimer.singleShot(0,self.fetch)

    def render_versions(self,*args):
        selected=self.version.text().strip();self.tree.clear();query=self.query.text().strip().lower()
        for entry in self.entries:
            if query not in entry.id.lower() or not self.snapshots.isChecked() and entry.type!='release':continue
            item=QTreeWidgetItem([entry.id,{'release':'正式版','snapshot':'快照','old_alpha':'Alpha','old_beta':'Beta'}.get(entry.type,entry.type),str(entry.release_time or '')[:10]])
            item.setData(0,Qt.ItemDataRole.UserRole,entry.id);self.tree.addTopLevelItem(item)
            if entry.id==selected:self.tree.setCurrentItem(item)

    def choose(self,item,previous=None):
        if item:self.version.setText(item.data(0,Qt.ItemDataRole.UserRole))

    def fetch(self):
        if self.loading or not self.active:return
        self.loading=True;self.retry.setEnabled(False);self.status.setText('正在获取版本列表…');repo=self.launcher.repo
        def done(manifest):
            self.loading=False
            if not self.active:return
            self.retry.setEnabled(True);self.entries=manifest.versions;self.render_versions();self.status.setText(f'可用版本 {len(self.entries)} 个；默认仅显示正式版。')
            if not self.version.text() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        def failed(error):
            self.loading=False
            if self.active:self.retry.setEnabled(True);self.status.setText('暂时无法获取版本列表。可以重试，或手动填写版本号。')
        self.launcher.tasks.submit(lambda job:repo.fetch_manifest(),done,failed)

    def install(self):
        version=self.version.text().strip();kind=self.loader.currentData();build=self.build.text().strip() if kind!='vanilla' else ''
        if not version:self.status.setText('请先选择或填写 Minecraft 版本号。');return
        repo=self.launcher.repo
        def work(job):
            progress=lambda a,b:job.emit((a,b))
            if kind=='vanilla':target=version
            elif kind in ('fabric','quilt'):
                from ..install.fabric import install_loader
                target=install_loader(repo,version,build or None,kind,job.emit)
            elif kind=='optifine':
                from ..install.optifine import install,pick_edition
                target=install(repo,version,pick_edition(repo.downloader,version,build),on_stage=job.emit,on_progress=progress)
            else:
                from ..install.forge import install_forge
                target=install_forge(repo,version,kind,build,job.emit,progress)
            repo.install(target,job.emit,progress);return target
        # Keep this dialog available if another mutation prevents starting.
        if self.launcher.task('安装 '+version,work,self.launcher.installed):self.accept()
