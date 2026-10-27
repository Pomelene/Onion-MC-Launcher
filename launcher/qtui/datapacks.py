"""Data pack management embedded in the current launcher window."""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QFileDialog,QMessageBox,QScrollArea,QWidget,QLineEdit,QTreeWidgetItem
from shiboken6 import isValid
from .widgets import column,row,label,button,ContentRow,Empty,clear
from ..datapacks import scan,import_zip,remove


class WorldDataPacks(QDialog):
    def __init__(self,owner,vid,world):
        super().__init__(owner);self.owner=owner;self.repo=owner.repo;self.vid=vid
        self.folder=Path(world.dir)/'datapacks';self.generation=0
        self.navigation_title='数据包 · '+world.name;self.setWindowTitle(self.navigation_title)
        body=column(self,24,12);bar=row();bar.addWidget(button('导入',self.add,'soft','plus'))
        bar.addWidget(button('下载',self.search_online,glyph='download'))
        bar.addWidget(button('打开目录',self.open_folder,glyph='folder'));bar.addWidget(button('刷新',self.refresh,glyph='refresh'));bar.addStretch();body.addLayout(bar)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container=QWidget();self.results=column(container,0,0);self.results.addStretch();scroll.setWidget(container);body.addWidget(scroll,1)
        self.status=label('','muted');body.addWidget(self.status)
        self.refresh()

    def refresh(self):
        self.generation+=1;generation=self.generation;self.status.setText('正在读取…')
        def done(items):
            if not isValid(self) or generation!=self.generation:return
            clear(self.results);self.status.setText('')
            if not items:self.results.addWidget(Empty('没有数据包','','package'));self.results.addStretch();return
            for entry in items:
                item=ContentRow(entry.path.name,entry.description,'package')
                item.action('打开所在目录',lambda:self.owner.open_folder(self.folder),'folder')
                item.action('移入恢复中心',lambda p=entry.path:self.remove(p),'trash','danger')
                self.results.addWidget(item)
            self.results.addStretch()
        self.owner.tasks.submit(lambda job:scan(self.folder),done,lambda error:self.owner.error(error) if isValid(self) else None)

    def open_folder(self):
        try:self.repo.assert_writable(self.folder);self.folder.mkdir(parents=True,exist_ok=True);self.owner.open_folder(self.folder)
        except Exception as error:self.owner.error(error)

    def add(self):
        path,_=QFileDialog.getOpenFileName(self,'导入数据包','','ZIP 数据包 (*.zip)')
        if not path:return
        def work(job):self.repo.assert_idle(self.vid);self.repo.assert_writable(self.folder/'probe');return import_zip(self.folder,Path(path))
        self.owner.task('导入数据包',work,lambda _:self.refresh() if isValid(self) else None,task_repo=self.repo,task_instance=self.vid)

    def search_online(self):
        try:game=self.repo.resolver.resolve(self.vid).game_version
        except Exception as error:self.owner.error(error);return
        self.owner.show_subpage(DataPackSearch(self.owner,self,game))

    def remove(self,path):
        if QMessageBox.question(self,'移除数据包','将 '+path.name+' 移入恢复中心？')!=QMessageBox.StandardButton.Yes:return
        def work(job):self.repo.assert_idle(self.vid);self.repo.assert_writable(path);return remove(self.folder,path)
        self.owner.task('移除数据包',work,lambda _:self.refresh() if isValid(self) else None,task_repo=self.repo,task_instance=self.vid)


class DataPackSearch(QDialog):
    def __init__(self,owner,manager,game):
        super().__init__(owner);self.owner=owner;self.manager=manager;self.repo=manager.repo;self.game=game;self.request=0;self.page=0;self.total=0;self.active=True
        self.navigation_title='下载数据包';self.setWindowTitle(self.navigation_title)
        body=column(self,24,12);bar=row();self.query=QLineEdit();self.query.setPlaceholderText('搜索数据包');bar.addWidget(self.query,1)
        bar.addWidget(button('搜索',lambda:self.search(0),'soft','search'));body.addLayout(bar)
        from .lists import FlatTreeWidget
        self.tree=FlatTreeWidget();self.tree.entities();body.addWidget(self.tree,1)
        footer=row();self.status=label('','muted');footer.addWidget(self.status,1)
        self.previous=button('上一页',lambda:self.search(self.page-1));self.next=button('下一页',lambda:self.search(self.page+1))
        footer.addWidget(self.previous);footer.addWidget(self.next);body.addLayout(footer)
        self.tree.itemDoubleClicked.connect(self.choose);self.query.returnPressed.connect(lambda:self.search(0))
        self.finished.connect(lambda _:setattr(self,'active',False));QTimer.singleShot(0,lambda:self.search(0))

    def search(self,page):
        from ..catalog import search
        self.request+=1;request=self.request;page=max(0,page);query=self.query.text().strip();self.status.setText('正在搜索…')
        self.previous.setEnabled(False);self.next.setEnabled(False)
        def done(data):
            if not self.active or not isValid(self) or request!=self.request:return
            from .lists import DETAIL_ROLE
            self.tree.clear();hits=data.get('hits') or [];self.total=int(data.get('total_hits') or 0);self.page=page
            for hit in hits:
                if not hit.get('project_id'):continue
                item=QTreeWidgetItem([hit.get('title') or hit.get('slug') or '数据包'])
                item.setData(0,DETAIL_ROLE,hit.get('description') or '');item.setData(0,Qt.ItemDataRole.UserRole,hit['project_id']);self.tree.addTopLevelItem(item)
            self.status.setText('双击选择版本' if hits else '没有匹配结果')
            self.previous.setEnabled(page>0);self.next.setEnabled((page+1)*20<self.total)
        def failed(error):
            if self.active and isValid(self) and request==self.request:self.status.setText('搜索失败，可重试')
        self.owner.tasks.submit(lambda job:search(self.repo.downloader,'datapack',query,self.game,limit=20,offset=page*20),done,failed,downloader=self.repo.downloader)

    def choose(self,item,column=0):
        from .project_versions import ProjectVersions
        project=item.data(0,Qt.ItemDataRole.UserRole)
        self.owner.show_subpage(ProjectVersions(self.owner,project,item.text(0),'datapack',self.game,'datapack',self.manager.vid,
                                               lambda release:self.install(project,release)))

    def install(self,project,release):
        from tempfile import TemporaryDirectory
        from ..catalog import versions,pick_version,download_version
        from ..download import DownloadCancelled
        repo,manager=self.repo,self.manager
        def work(job):
            repo.assert_idle(manager.vid);repo.assert_writable(manager.folder/'probe')
            chosen=pick_version([v for v in versions(repo.downloader,project) if v.get('id')==release],self.game,'datapack')
            if not chosen:raise ValueError('该数据包版本与当前游戏不兼容')
            cache=repo.cache_path('datapacks')
            cache.mkdir(parents=True,exist_ok=True)
            with TemporaryDirectory(dir=cache,prefix='download-') as tmp:
                job.emit('正在下载数据包');path=download_version(repo.downloader,chosen,Path(tmp))
                if job.cancel.is_set():raise DownloadCancelled('下载已取消')
                return import_zip(manager.folder,path)
        def done(path):
            self.owner.status.setText('数据包已安装 · '+path.name)
            if isValid(manager):manager.refresh()
        return self.owner.task('安装数据包',work,done,task_repo=repo,task_instance=manager.vid)
