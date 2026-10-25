"""Select a component version for a fixed, existing instance."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidgetItem
from .lists import FlatTreeWidget,DETAIL_ROLE
from .widgets import column,row,label,button
from ..components import component_info


class ComponentVersions(QDialog):
    def __init__(self,owner,vid,kind):
        super().__init__(owner);self.owner=owner;self.repo=owner.repo;self.vid=vid;self.kind=kind;self.active=True;self.loading=False;self.job=None
        self.game,current,self.current_version=component_info(self.repo,vid)
        if current and current!=kind:raise ValueError('与当前 '+current+' 加载器不兼容')
        self.navigation_title=kind.title()+' · '+owner.instances.display_name(vid);self.setWindowTitle(self.navigation_title)
        body=column(self,20,12);top=row();top.addWidget(label('Minecraft '+self.game+(' · 当前 '+self.current_version if self.current_version else ''),'muted'),1)
        self.refresh_button=button('',self.fetch,glyph='refresh');self.refresh_button.setToolTip('刷新版本');self.refresh_button.setAccessibleName('刷新版本');top.addWidget(self.refresh_button);body.addLayout(top)
        self.tree=FlatTreeWidget();self.tree.setColumnCount(1);self.tree.setHeaderHidden(True);body.addWidget(self.tree,1)
        footer=row();self.status=label('','muted',True);footer.addWidget(self.status,1);self.install_button=button('更换版本' if self.current_version else '安装',self.install,'primary','download');footer.addWidget(self.install_button);body.addLayout(footer)
        self.tree.currentItemChanged.connect(self.selection);self.tree.itemDoubleClicked.connect(lambda *_:self.install())
        self.finished.connect(self.closed);self.selection();QTimer.singleShot(0,self.fetch)

    def closed(self,*args):
        self.active=False
        if self.job:self.job.cancel.set()

    def selection(self,*args):
        item=self.tree.currentItem();value=item.data(0,Qt.ItemDataRole.UserRole) if item else ''
        self.install_button.setEnabled(not self.loading and bool(value) and value!=self.current_version)
        self.install_button.setText('已安装' if value and value==self.current_version else '更换版本' if self.current_version else '安装')

    def fetch(self):
        if not self.active or self.loading:return
        from ..install.fabric import list_loaders
        self.loading=True;self.refresh_button.setEnabled(False);self.selection();self.status.setText('正在获取版本…')
        def done(entries):
            if not self.active:return
            self.loading=False;self.refresh_button.setEnabled(True);self.tree.clear();selected=None;preferred=None
            for entry in entries:
                loader=entry.get('loader') or {};value=loader.get('version')
                if not value:continue
                item=QTreeWidgetItem([value]);item.setData(0,Qt.ItemDataRole.UserRole,value)
                item.setData(0,DETAIL_ROLE,('当前 · ' if value==self.current_version else '')+('稳定版' if loader.get('stable') else '测试版'));self.tree.addTopLevelItem(item)
                if value==self.current_version:selected=item
                if preferred is None and loader.get('stable'):preferred=item
            if self.tree.topLevelItemCount():self.tree.setCurrentItem(selected or preferred or self.tree.topLevelItem(0))
            self.status.setText('' if self.tree.topLevelItemCount() else '没有适用版本');self.selection()
        def failed(error):
            if self.active:self.loading=False;self.refresh_button.setEnabled(True);self.status.setText('获取失败，可刷新重试');self.selection()
        self.job=self.owner.tasks.submit(lambda job:list_loaders(self.repo.downloader,self.kind,self.game),done,failed,downloader=self.repo.downloader)

    def install(self):
        item=self.tree.currentItem();version=item.data(0,Qt.ItemDataRole.UserRole) if item else ''
        if self.loading or not version or version==self.current_version:return
        owner,repo,vid,kind,game=self.owner,self.repo,self.vid,self.kind,self.game
        def work(job):
            from ..components import replace_loader
            return replace_loader(repo,vid,kind,version,job.emit,lambda a,b:job.emit((a,b)),job.cancel,expected_game=game)
        def done(result):
            owner.reload_versions(refresh_page=False)
            if owner.repo is repo and owner.selected_version==vid and owner.current_page=='instance' and owner.instance_tab=='auto':owner.instance_workspace.build_auto()
            owner.status.setText(kind.title()+' 已更换为 '+version)
        def start():
            if owner.repo is not repo:owner.error('游戏目录已切换，请回到原实例重新操作');return
            return owner.task('安装 '+kind.title()+' '+version,work,done,retry=start,task_repo=repo,task_instance=vid)
        if start():self.accept()
