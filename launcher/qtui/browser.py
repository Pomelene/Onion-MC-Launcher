"""Persistent content browser: fixed controls, one scrolling result surface."""
from .choices import ChoiceComboBox
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QLineEdit,QComboBox
from .widgets import Page,Empty,ContentRow,column,row,label,button,clear,icon_button

TITLES={'mod':'模组','resourcepack':'资源包','shader':'光影','modpack':'整合包'}


class ContentBrowser(QWidget):
    PAGE_SIZE=20

    def __init__(self,launcher,kind):
        super().__init__();self.launcher=launcher;self.repo=launcher.repo;self.kind=kind
        self.request_id=0;self.loading=False;self.page_number=0;self.total=0;self.target_vid='';self.last_search=None
        body=column(self,20,10)
        toolbar=row(spacing=8);self.target=ChoiceComboBox();self.target.setMinimumWidth(130);self.target.setMaximumWidth(250);self.target.setAccessibleName('安装到实例');toolbar.addWidget(self.target,1)
        self.query=QLineEdit();self.query.setPlaceholderText('搜索'+TITLES[kind]);self.query.setClearButtonEnabled(True);toolbar.addWidget(self.query,2)
        self.go=icon_button('搜索',lambda:self.search(0),'search');toolbar.addWidget(self.go)
        self.filter_button=icon_button('筛选版本',lambda:self.filters.setVisible(self.filter_button.isChecked()),'settings');self.filter_button.setCheckable(True);toolbar.addWidget(self.filter_button);body.addLayout(toolbar)
        self.filters=QWidget();filters=row(self.filters,0,8);self.filters.hide();body.addWidget(self.filters)
        self.game=QLineEdit();self.game.setPlaceholderText('游戏版本');self.game.setAccessibleName('游戏版本');self.game.setToolTip('筛选 Minecraft 版本');self.game.setMaximumWidth(160);filters.addWidget(self.game)
        self.loader=ChoiceComboBox();self.loader.setFixedWidth(136)
        for title,value in [('不限加载器',''),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt')]:self.loader.addItem(title,value)
        self.loader.setEnabled(kind in ('mod','modpack'));self.loader.setVisible(kind in ('mod','modpack'));self.loader.setAccessibleName('加载器');filters.addWidget(self.loader)
        self.reset=icon_button('恢复实例的版本筛选',self.match_target,'refresh');filters.addWidget(self.reset);filters.addStretch()
        self.summary=label('','muted');self.summary.hide()
        self.results=Page();self.results.body.setSpacing(0);body.addWidget(self.results,1)
        self.footer=QWidget();footer=row(self.footer,0,8);self.message=label('','muted');footer.addWidget(self.message,1)
        self.previous=icon_button('上一页',lambda:self.search(self.page_number-1),'back');self.next=icon_button('下一页',lambda:self.search(self.page_number+1),'arrow');footer.addWidget(self.previous)
        self.page_label=label('1 / 1','muted');footer.addWidget(self.page_label);footer.addWidget(self.next);body.addWidget(self.footer)
        self.query.returnPressed.connect(lambda:self.search(0));self.target.currentIndexChanged.connect(self.target_changed)
        self.game.textEdited.connect(self.invalidate_search);self.loader.activated.connect(self.invalidate_search)
        self.sync_target();self.empty();self.update_paging()

    def sync_target(self):
        self.target.blockSignals(True);self.target.clear()
        if self.kind=='modpack':self.target.addItem('新建独立实例','');self.target.hide()
        else:
            for vid in self.launcher.versions:self.target.addItem(self.launcher.instances.display_name(vid),vid)
            if not self.launcher.versions:self.target.addItem('尚未选择实例','')
        vid=self.launcher.selected_version if self.kind!='modpack' else ''
        self.target.setCurrentIndex(max(0,self.target.findData(vid)));self.target.blockSignals(False)
        if self.target_vid!=vid:
            self.request_id+=1;self.loading=False;self.go.setEnabled(True);self.last_search=None;self.target_vid=vid
            self.match_target();self.empty();self.update_paging()
        self.update_context()

    def update_context(self):
        self.target.setToolTip('安装到：'+self.target.currentText())
        self.filter_button.setToolTip('筛选版本：'+' · '.join(v for v in (self.game.text(),self.loader.currentText() if self.loader.isEnabled() else '') if v))

    def target_changed(self,index):
        vid=self.target.currentData() or ''
        if vid and vid!=self.launcher.selected_version:
            if not self.launcher.set_selected(vid,refresh_page=False):self.sync_target();return
        self.sync_target()

    def match_target(self):
        if self.target_vid:
            from ..modpack import _base_version,_detect_loader
            from ..version import VersionNotFound
            try:
                self.game.setText(_base_version(self.repo,self.target_vid));self.loader.setCurrentIndex(max(0,self.loader.findData(_detect_loader(self.repo,self.target_vid)[0])))
            except (VersionNotFound,ValueError,OSError):pass
        else:self.game.clear();self.loader.setCurrentIndex(0)
        if self.last_search is not None:self.invalidate_search()

    def invalidate_search(self,*args):
        self.request_id+=1;self.loading=False;self.go.setEnabled(True);self.last_search=None;self.empty();self.update_paging()

    def empty(self):
        clear(self.results.body);self.total=0;self.page_number=0
        self.summary.setText('');self.message.setText('')

    def update_paging(self):
        pages=max(1,(self.total+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        self.page_label.setText(f'{self.page_number+1} / {pages}')
        self.previous.setEnabled(not self.loading and self.page_number>0)
        self.next.setEnabled(not self.loading and self.last_search is not None and (self.page_number+1)*self.PAGE_SIZE<self.total)
        for control in (self.previous,self.next,self.page_label):control.setVisible(pages>1)
        self.footer.setVisible(pages>1 or bool(self.message.text()))

    def search(self,page=0):
        text=self.query.text().strip()
        query=(text,self.game.text().strip(),self.loader.currentData() if self.loader.isEnabled() else '',self.target_vid)
        if query!=self.last_search:page=0
        page=max(0,page);self.request_id+=1;request=self.request_id;self.loading=True;self.go.setEnabled(False);self.message.setText('正在搜索…');self.update_paging()
        def done(data):
            if request!=self.request_id:return
            self.loading=False;self.go.setEnabled(True);self.last_search=query;self.page_number=page
            hits=data.get('hits') or [];self.total=max(int(data.get('total_hits') or 0),page*self.PAGE_SIZE+len(hits))
            clear(self.results.body)
            if not hits:self.results.body.addWidget(Empty('没有匹配结果','试试其他关键词，或放宽游戏版本和加载器条件。','search'))
            for hit in hits:
                title=hit.get('title') or hit.get('slug') or '项目'
                detail=hit.get('description') or hit.get('author') or ''
                item=ContentRow(title,detail,{'mod':'package','resourcepack':'grid','shader':'world','modpack':'package'}[self.kind])
                item.action('选择版本',lambda pid=hit['project_id'],t=title:self.launcher.choose_project_version(pid,t,self.kind,query[1],query[2],query[3]),'arrow')
                self.results.body.addWidget(item)
                if hit.get('icon_url'):self.launcher.load_catalog_icon(item,hit['icon_url'])
            self.summary.setText('');self.message.setText('');self.update_paging()
            QTimer.singleShot(0,self.results,lambda:self.results.verticalScrollBar().setValue(0))
        def failed(error):
            if request!=self.request_id:return
            self.loading=False;self.go.setEnabled(True);self.message.setText('搜索失败，可重试：'+str(error));self.update_paging()
        from ..catalog import search
        self.launcher.tasks.submit(lambda job:search(self.repo.downloader,self.kind,*query[:3],limit=self.PAGE_SIZE,offset=page*self.PAGE_SIZE),done,failed)
