"""Version-first installation dialog, using the existing installer services."""
from .choices import ChoiceComboBox
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QLineEdit,QTreeWidgetItem,QWidget,QLayout
from .widgets import column,row,label,button,icon,ContentCheck
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE


class InstallDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.launcher=window;self.entries=[];self.loading=False;self.active=True
        self.setWindowTitle('安装 Minecraft');self.resize(940,670)
        body=column(self,20,12);body.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        search=row();self.query=QLineEdit();self.query.setPlaceholderText('筛选版本，例如 1.21');search.addWidget(self.query,1)
        self.snapshots=ContentCheck();self.snapshots.setAccessibleName('显示快照与旧版');search.addWidget(self.snapshots)
        snapshots_label=label('快照与旧版','muted');snapshots_label.mousePressEvent=lambda event:self.snapshots.click() if event.button()==Qt.MouseButton.LeftButton else None;search.addWidget(snapshots_label)
        self.retry=button('',self.refresh,glyph='refresh');self.retry.setFixedWidth(36);self.retry.setToolTip('刷新版本列表');self.retry.setAccessibleName('刷新版本列表');search.addWidget(self.retry);body.addLayout(search)
        panels=row(spacing=16);body.addLayout(panels,1)
        self.tree=QTreeWidget();self.tree.setColumnCount(1);self.tree.setHeaderHidden(True);self.tree.setMinimumHeight(180);panels.addWidget(self.tree,1)
        self.loader_panel=QWidget();loader_body=column(self.loader_panel,0,8)
        self.loader_tree=QTreeWidget();self.loader_tree.setAccessibleName('加载器版本');self.loader_tree.setColumnCount(1);self.loader_tree.setHeaderHidden(True);self.loader_tree.setMinimumHeight(180);loader_body.addWidget(self.loader_tree,1)
        self.loader_status=label('','muted',True);self.loader_status.hide();loader_body.addWidget(self.loader_status);panels.addWidget(self.loader_panel,1);self.loader_panel.hide()
        fields=row(spacing=16);body.addLayout(fields)
        def field(title,control,stretch=0):
            group=column(spacing=6);group.addWidget(label(title,'muted'));group.addWidget(control);fields.addLayout(group,stretch)
        self.version=QLineEdit();self.version.setMaximumWidth(170);self.version.setPlaceholderText('选择或输入版本');field('游戏版本',self.version)
        self.loader=ChoiceComboBox();self.loader.setMinimumWidth(150)
        for title,key in [('原版 Minecraft','vanilla'),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt'),('OptiFine','optifine')]:self.loader.addItem(title,key)
        field('加载器',self.loader)
        self.instance_name=QLineEdit();self.instance_name.setPlaceholderText('实例名称');field('实例名称',self.instance_name,1);self.custom_name=False
        self.instance_name.textEdited.connect(lambda _:setattr(self,'custom_name',True))
        def suggest_name(*args):
            from ..instance import default_instance_name
            if not self.custom_name:self.instance_name.setText(default_instance_name(self.version.text().strip(),self.loader.currentData()) if self.version.text().strip() else '')
        self.version.textChanged.connect(suggest_name);self.loader.currentIndexChanged.connect(suggest_name)
        self.build=QLineEdit(self);self.build.setReadOnly(True);self.build.setEnabled(False);self.build.hide()
        self.loader_seq=0;self.loader_timer=QTimer(self);self.loader_timer.setSingleShot(True);self.loader_timer.setInterval(350);self.loader_timer.timeout.connect(self.fetch_loaders)
        actions=row();self.status=label('正在获取版本列表…','muted',True);actions.addWidget(self.status,1)
        self.install_button=button('开始安装',self.install,'primary','download');self.install_button.setEnabled(False);self.install_button.setToolTip(str(window.repo.game_dir));actions.addWidget(self.install_button);body.addLayout(actions)
        self.query.textChanged.connect(self.render_versions);self.snapshots.toggled.connect(self.render_versions)
        self.loader.currentIndexChanged.connect(lambda:self.build.setEnabled(self.loader.currentData()!='vanilla'))
        def schedule_loaders(*args):
            self.loader_seq+=1;self.build.clear();self.loader_tree.clear();vanilla=self.loader.currentData()=='vanilla'
            self.loader_panel.setVisible(not vanilla);self.loader_tree.setAccessibleName(self.loader.currentText()+' 版本')
            self.install_button.setEnabled(vanilla and bool(self.version.text().strip()))
            self.loader_status.setText('正在获取版本…' if not vanilla else '')
            self.loader_status.setVisible(not vanilla)
            if vanilla:self.loader_timer.stop()
            else:self.loader_timer.start()
        self.loader.currentIndexChanged.connect(schedule_loaders);self.version.textChanged.connect(schedule_loaders)
        self.loader_tree.currentItemChanged.connect(lambda item,previous:self.choose_loader(item))
        self.tree.currentItemChanged.connect(self.choose);self.tree.itemDoubleClicked.connect(lambda *_:self.install())
        self.finished.connect(lambda _:setattr(self,'active',False));QTimer.singleShot(0,self.fetch)

    def render_versions(self,*args):
        selected=self.version.text().strip();self.tree.clear();query=self.query.text().strip().lower()
        for entry in self.entries:
            if query not in entry.id.lower() or not self.snapshots.isChecked() and entry.type!='release':continue
            kind={'release':'正式版','snapshot':'快照','old_alpha':'Alpha','old_beta':'Beta'}.get(entry.type,entry.type)
            date=str(entry.release_time or '')[:10];detail=' · '.join(value for value in (kind if self.snapshots.isChecked() else '',date) if value) or kind
            item=QTreeWidgetItem([entry.id]);item.setData(0,DETAIL_ROLE,detail);item.setIcon(0,icon('package'))
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
            self.retry.setEnabled(True);self.entries=manifest.versions;self.render_versions();self.status.setText('')
            if not self.version.text() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        def failed(error):
            self.loading=False
            if self.active:self.retry.setEnabled(True);self.status.setText('暂时无法获取版本列表。可以重试，或手动填写版本号。')
        self.launcher.tasks.submit(lambda job:repo.fetch_manifest(),done,failed)

    def refresh(self):
        self.fetch()
        if self.loader.currentData()!='vanilla':self.fetch_loaders()

    def install(self):
        version=self.version.text().strip();kind=self.loader.currentData();build=self.build.text().strip() if kind!='vanilla' else ''
        if not version:self.status.setText('请先选择或填写 Minecraft 版本号。');return
        if kind!='vanilla' and not build:self.loader_status.setText('请选择加载器版本');self.loader_status.show();return
        repo=self.launcher.repo
        from ..instance import default_instance_name
        name=self.instance_name.text().strip() or default_instance_name(version,kind)
        from ..install.instance import next_instance_id
        import uuid
        try:target_id=next_instance_id(repo,name)
        except ValueError as error:self.status.setText(str(error));return
        request_id=uuid.uuid4().hex
        def work(job):
            from ..install.instance import install_instance
            return install_instance(repo,version,kind,build,target_id,request_id,job.emit,lambda a,b:job.emit((a,b)),job.cancel)
        # Keep this dialog available if another mutation prevents starting.
        def installed(target):
            if not self.launcher.instances.get(target).name:
                self.launcher.instances.update(target,name=name)
            self.launcher.installed(target)
        owner=self.launcher
        def start():
            if owner.repo is not repo:owner.error('游戏目录已切换，请回到原目录重新安装');return
            return owner.task('安装 '+version,work,installed,retry=start,task_repo=repo,task_instance=target_id)
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
            self.loader_status.setText('' if kind=='vanilla' else '请先选择游戏版本');self.loader_status.setVisible(kind!='vanilla');self.loader_panel.setVisible(kind!='vanilla');self.install_button.setEnabled(kind=='vanilla' and bool(game));return
        self.install_button.setEnabled(False);self.loader_status.setText('正在获取版本…');self.loader_status.show();repo=self.launcher.repo
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
                item=QTreeWidgetItem([value]);item.setData(0,DETAIL_ROLE,channel);item.setData(0,Qt.ItemDataRole.UserRole,value);self.loader_tree.addTopLevelItem(item)
                if preferred is None and channel in ('稳定版','正式版'):preferred=item
            if entries:self.loader_tree.setCurrentItem(preferred or self.loader_tree.topLevelItem(0))
            self.loader_status.setText('' if entries else '没有适用版本')
            self.loader_status.setVisible(not bool(entries))
        def failed(error):
            if self.active and seq==self.loader_seq:self.loader_status.setText('获取失败，可刷新重试');self.loader_status.show()
        self.launcher.tasks.submit(work,done,failed)
