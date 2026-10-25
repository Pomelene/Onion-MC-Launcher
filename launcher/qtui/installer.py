"""Version-first installation dialog, using the existing installer services."""
from .choices import ChoiceComboBox
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QLineEdit,QComboBox,QCheckBox,QTreeWidget,QTreeWidgetItem,QWidget
from .widgets import column,row,label,button,Card


class InstallDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.launcher=window;self.entries=[];self.loading=False;self.active=True
        self.setWindowTitle('安装 Minecraft');self.resize(940,670);self.setMinimumSize(820,570)
        body=column(self,26,18);body.addWidget(label('安装 Minecraft','title'))
        panels=row(spacing=20);body.addLayout(panels,1)
        left=QWidget();list_body=column(left,0,12);panels.addWidget(left,3)
        search=row();self.query=QLineEdit();self.query.setPlaceholderText('筛选版本，例如 1.21');search.addWidget(self.query,1)
        self.snapshots=QCheckBox('快照与旧版');search.addWidget(self.snapshots);list_body.addLayout(search)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['游戏版本','类型','发布时间']);self.tree.setRootIsDecorated(False);self.tree.setColumnWidth(0,150);self.tree.setColumnWidth(1,85);list_body.addWidget(self.tree,1)
        self.status=label('正在获取版本列表…','muted',True);list_body.addWidget(self.status)
        self.retry=button('刷新版本列表',self.fetch,glyph='history');list_body.addWidget(self.retry,alignment=Qt.AlignmentFlag.AlignLeft)
        options=Card('安装选项');options.setFixedWidth(290);panels.addWidget(options)
        options.body.addWidget(label('Minecraft 版本','heading'));self.version=QLineEdit();self.version.setPlaceholderText('从左侧选择，或输入版本号');options.body.addWidget(self.version)
        options.body.addWidget(label('模组加载器','heading'));self.loader=ChoiceComboBox()
        for title,key in [('原版 Minecraft','vanilla'),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt'),('OptiFine','optifine')]:self.loader.addItem(title,key)
        options.body.addWidget(self.loader)
        self.instance_name=QLineEdit();self.instance_name.setPlaceholderText('版本号 + 加载器');options.body.addWidget(label('实例名称','heading'));options.body.addWidget(self.instance_name);self.custom_name=False
        self.instance_name.textEdited.connect(lambda _:setattr(self,'custom_name',True))
        def suggest_name(*args):
            from ..instance import default_instance_name
            if not self.custom_name:self.instance_name.setText(default_instance_name(self.version.text().strip(),self.loader.currentData()) if self.version.text().strip() else '')
        self.version.textChanged.connect(suggest_name);self.loader.currentIndexChanged.connect(suggest_name)
        self.build=QLineEdit();self.build.setReadOnly(True);self.build.setPlaceholderText('从版本表选择');self.build.setEnabled(False);options.body.addWidget(label('加载器版本','muted'));options.body.addWidget(self.build)
        loader_bar=row();loader_bar.addWidget(label('可用加载器版本','heading'),1);loader_bar.addWidget(button('刷新',self.fetch_loaders,glyph='history'));list_body.addLayout(loader_bar)
        self.loader_tree=QTreeWidget();self.loader_tree.setRootIsDecorated(False);self.loader_tree.setHeaderLabels(['加载器版本','渠道','Minecraft']);self.loader_tree.setColumnWidth(0,210);self.loader_tree.setMaximumHeight(200);list_body.addWidget(self.loader_tree)
        self.loader_status=label('选择模组加载器后列出适用版本。','muted',True);list_body.addWidget(self.loader_status)
        self.loader_seq=0;self.loader_timer=QTimer(self);self.loader_timer.setSingleShot(True);self.loader_timer.setInterval(350);self.loader_timer.timeout.connect(self.fetch_loaders)
        options.body.addStretch()
        options.body.addWidget(label('下载位置','eyebrow'));options.body.addWidget(label(str(window.repo.game_dir),'muted',True))
        actions=row();actions.addStretch();actions.addWidget(button('取消',self.reject));self.install_button=button('开始安装',self.install,'primary','download');actions.addWidget(self.install_button);body.addLayout(actions)
        self.query.textChanged.connect(self.render_versions);self.snapshots.toggled.connect(self.render_versions)
        self.loader.currentIndexChanged.connect(lambda:self.build.setEnabled(self.loader.currentData()!='vanilla'))
        def schedule_loaders(*args):
            self.loader_seq+=1;self.build.clear();self.loader_tree.clear();self.install_button.setEnabled(self.loader.currentData()=='vanilla');self.loader_timer.start()
        self.loader.currentIndexChanged.connect(schedule_loaders);self.version.textChanged.connect(schedule_loaders)
        self.loader_tree.currentItemChanged.connect(lambda item,previous:self.choose_loader(item))
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
        if kind!='vanilla' and not build:self.loader_status.setText('请从加载器版本表选择一个可用版本。');return
        repo=self.launcher.repo
        from ..instance import default_instance_name
        name=self.instance_name.text().strip() or default_instance_name(version,kind)
        def work(job):
            progress=lambda a,b:job.emit((a,b))
            if kind=='vanilla':target=version
            elif kind in ('fabric','quilt'):
                from ..install.fabric import install_loader
                target=install_loader(repo,version,build or None,kind,job.emit)
            elif kind=='optifine':
                from ..install.optifine import install,pick_edition
                from ..java import resolve_java
                base=repo.install(version,job.emit,progress)
                java=resolve_java(base.java_major or 8,self.launcher.config_obj.get('java_path'),repo.downloader,job.emit,progress)
                if not java:raise RuntimeError('安装 OptiFine 需要可用的 Java。')
                edition=pick_edition(repo.downloader,version,build)
                if edition is None:raise RuntimeError('所选 OptiFine 版本已不可用，请刷新版本表。')
                target=install(repo,version,edition,java_path=str(java.path),on_stage=job.emit,on_progress=progress)
            else:
                from ..install.forge import install_forge
                target=install_forge(repo,version,kind,build,job.emit,progress)
            repo.install(target,job.emit,progress);return target
        # Keep this dialog available if another mutation prevents starting.
        def installed(target):
            if not self.launcher.instances.get(target).name:
                self.launcher.instances.update(target,name=name)
            self.launcher.installed(target)
        owner=self.launcher
        def start():
            if owner.repo is not repo:owner.error('游戏目录已切换，请回到原目录重新安装');return
            return owner.task('安装 '+version,work,installed,retry=start,task_repo=repo,task_instance=version)
        if start():self.accept()

    def choose_loader(self,item):
        self.build.setText(item.data(0,Qt.ItemDataRole.UserRole) if item else '')
        self.install_button.setEnabled(self.loader.currentData()=='vanilla' or bool(item))

    def fetch_loaders(self):
        if not self.active:return
        self.loader_timer.stop()
        self.loader_seq+=1;seq=self.loader_seq;kind=self.loader.currentData();game=self.version.text().strip()
        self.loader_tree.clear();self.build.clear()
        if kind=='vanilla' or not game:
            self.loader_status.setText('原版无需加载器。' if kind=='vanilla' else '请先选择 Minecraft 版本。');self.install_button.setEnabled(kind=='vanilla');return
        self.install_button.setEnabled(False);self.loader_status.setText('正在获取 '+self.loader.currentText()+' 版本表…');repo=self.launcher.repo
        def work(job):
            if kind in ('fabric','quilt'):
                from ..install.fabric import list_loaders
                return [(e['loader']['version'],'稳定版' if e['loader'].get('stable') else '预览版') for e in list_loaders(repo.downloader,kind,game) if (e.get('loader') or {}).get('version')]
            if kind in ('forge','neoforge'):
                from ..install.forge import list_versions
                return [(v,'测试版' if 'beta' in v.lower() else '正式版') for v in list_versions(repo,kind,game)]
            from ..install.optifine import list_editions
            return [(e['label'],'预览版' if e.get('preview') else '稳定版') for e in list_editions(repo.downloader,game)]
        def done(entries):
            if not self.active or seq!=self.loader_seq:return
            preferred=None
            for value,channel in entries:
                item=QTreeWidgetItem([value,channel,game]);item.setData(0,Qt.ItemDataRole.UserRole,value);self.loader_tree.addTopLevelItem(item)
                if preferred is None and channel in ('稳定版','正式版'):preferred=item
            if entries:self.loader_tree.setCurrentItem(preferred or self.loader_tree.topLevelItem(0))
            self.loader_status.setText(f'{len(entries)} 个适用版本 · 点击版本行选择' if entries else '没有找到适用于此游戏版本的加载器。')
        def failed(error):
            if self.active and seq==self.loader_seq:self.loader_status.setText('获取失败，可点击刷新重试：'+str(error))
        self.launcher.tasks.submit(work,done,failed)
