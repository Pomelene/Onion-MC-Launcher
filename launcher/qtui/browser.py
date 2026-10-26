"""Persistent content browser: fixed controls, one scrolling result surface."""
from .choices import ChoiceComboBox
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QLineEdit,QComboBox,QGridLayout
from shiboken6 import isValid
from ..catalog_search import SORTS,CATEGORY_LABELS,search_terms
from .widgets import Page,Empty,ContentRow,column,row,label,button,clear,icon_button

TITLES={'mod':'模组','resourcepack':'资源包','shader':'光影','modpack':'整合包'}


class ContentBrowser(QWidget):
    PAGE_SIZE=20

    def __init__(self,launcher,kind):
        super().__init__();self.launcher=launcher;self.repo=launcher.repo;self.kind=kind
        self.request_id=0;self.loading=False;self.page_number=0;self.total=0;self.target_vid='';self.last_search=None
        self.initialized=False;self.search_job=None;self.categories_loaded=False;self.categories_loading=False
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(350);self.search_timer.timeout.connect(lambda:self.search(0))
        body=column(self,20,10)
        toolbar=row(spacing=8);self.target=ChoiceComboBox();self.target.setMinimumWidth(130);self.target.setMaximumWidth(250);self.target.setAccessibleName('安装到实例');toolbar.addWidget(self.target,1)
        self.query=QLineEdit();self.query.setPlaceholderText('搜索'+TITLES[kind]);self.query.setToolTip('支持名称、关键词和常用中文别名；按回车搜索');self.query.setClearButtonEnabled(True);toolbar.addWidget(self.query,2)
        self.go=icon_button('搜索',lambda:self.search(0),'search');toolbar.addWidget(self.go)
        self.filter_button=icon_button('筛选',self.toggle_filters,'settings');self.filter_button.setCheckable(True);toolbar.addWidget(self.filter_button);body.addLayout(toolbar)
        self.filters=QWidget();filters=QGridLayout(self.filters);filters.setContentsMargins(0,0,0,0);filters.setSpacing(8);self.filters.hide();body.addWidget(self.filters)
        self.game=QLineEdit();self.game.setPlaceholderText('全部游戏版本');self.game.setAccessibleName('游戏版本');self.game.setToolTip('筛选 Minecraft 版本；留空为全部');filters.addWidget(self.game,0,0)
        self.loader=ChoiceComboBox()
        for title,value in [('不限加载器',''),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt')]:self.loader.addItem(title,value)
        self.loader.setEnabled(kind in ('mod','modpack'));self.loader.setVisible(kind in ('mod','modpack'));self.loader.setAccessibleName('加载器');filters.addWidget(self.loader,0,1)
        self.category=ChoiceComboBox();self.category.addItem('全部分类','');self.category.setAccessibleName('分类');filters.addWidget(self.category,1,0)
        self.sort=ChoiceComboBox();self.sort.setAccessibleName('排序')
        for title,value in SORTS:self.sort.addItem(title,value)
        filters.addWidget(self.sort,1,1)
        self.reset=icon_button('恢复默认筛选',self.reset_filters,'refresh');filters.addWidget(self.reset,0,2);filters.setColumnStretch(0,1);filters.setColumnStretch(1,1)
        self.summary=label('','muted');self.summary.hide()
        self.results=Page();self.results.body.setSpacing(0);body.addWidget(self.results,1)
        self.footer=QWidget();footer=row(self.footer,0,8);self.message=label('','muted');footer.addWidget(self.message,1)
        self.previous=icon_button('上一页',lambda:self.search(self.page_number-1),'back');self.next=icon_button('下一页',lambda:self.search(self.page_number+1),'arrow');footer.addWidget(self.previous)
        self.page_label=label('1 / 1','muted');footer.addWidget(self.page_label);footer.addWidget(self.next);body.addWidget(self.footer)
        self.query.returnPressed.connect(lambda:self.search(0));self.target.currentIndexChanged.connect(self.target_changed)
        self.query.textChanged.connect(self.edit_query)
        self.game.textEdited.connect(self.filters_changed);self.game.returnPressed.connect(lambda:self.search(0))
        for control in (self.loader,self.category,self.sort):control.activated.connect(self.filters_changed)
        self.sync_target();self.empty();self.update_paging()

    def showEvent(self,event):
        super().showEvent(event)
        if not self.initialized:QTimer.singleShot(0,self,self.initial_search)

    def initial_search(self):
        if self.isVisible() and not self.initialized:self.search(0)

    def edit_query(self,*args):
        self.invalidate_search()
        if not self.query.text().strip():self.search_timer.start()

    def filters_changed(self,*args):
        self.invalidate_search();self.update_context();self.search_timer.start()

    def toggle_filters(self):
        self.filters.setVisible(self.filter_button.isChecked())
        if not self.filters.isVisible() or self.categories_loaded or self.categories_loading:return
        self.categories_loading=True
        from ..catalog import categories
        def done(values):
            if not isValid(self):return
            self.categories_loading=False;self.categories_loaded=True;selected=self.category.currentData();self.category.setToolTip('')
            self.category.blockSignals(True);self.category.clear();self.category.addItem('全部分类','')
            for value in values:self.category.addItem(CATEGORY_LABELS.get(value,value),value)
            self.category.setCurrentIndex(max(0,self.category.findData(selected)));self.category.blockSignals(False)
        def failed(error):
            if not isValid(self):return
            self.categories_loading=False;self.category.setToolTip('分类加载失败；重新展开筛选可重试')
        self.launcher.tasks.submit(lambda job:categories(self.repo.downloader,self.kind),done,failed,downloader=self.repo.downloader)

    def reset_filters(self):
        self.category.setCurrentIndex(0);self.sort.setCurrentIndex(0);self.match_target();self.filters_changed()

    def sync_target(self):
        self.target.blockSignals(True);self.target.clear()
        if self.kind=='modpack':self.target.addItem('新建独立实例','');self.target.hide()
        else:
            for vid in self.launcher.versions:self.target.addItem(self.launcher.instances.display_name(vid),vid)
            if not self.launcher.versions:self.target.addItem('尚未选择实例','')
        vid=self.launcher.selected_version if self.kind!='modpack' else ''
        self.target.setCurrentIndex(max(0,self.target.findData(vid)));self.target.blockSignals(False)
        if self.target_vid!=vid:
            self.invalidate_search();self.target_vid=vid
            self.match_target();self.empty();self.update_paging()
            if self.initialized:self.search_timer.start()
        self.update_context()

    def update_context(self):
        self.target.setToolTip('安装到：'+self.target.currentText())
        self.filter_button.setToolTip(' · '.join(v for v in (self.game.text() or '全部版本',self.loader.currentText() if self.loader.isEnabled() else '',self.category.currentText(),self.sort.currentText()) if v))

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
            except (VersionNotFound,ValueError,OSError):self.game.clear();self.loader.setCurrentIndex(0)
        else:self.game.clear();self.loader.setCurrentIndex(0)
        self.update_context()

    def invalidate_search(self,*args):
        self.search_timer.stop();self.request_id+=1;self.loading=False;self.go.setEnabled(True)
        if self.search_job:self.search_job.cancel_job();self.search_job=None
        self.last_search=None;self.message.setText('');self.update_paging()

    def empty(self):
        clear(self.results.body);self.total=0;self.page_number=0
        self.summary.setText('');self.message.setText('')

    def update_paging(self):
        pages=max(1,(self.total+self.PAGE_SIZE-1)//self.PAGE_SIZE)
        self.page_label.setText(f'{self.page_number+1} / {pages}')
        self.previous.setEnabled(not self.loading and self.last_search is not None and self.page_number>0)
        self.next.setEnabled(not self.loading and self.last_search is not None and (self.page_number+1)*self.PAGE_SIZE<self.total)
        for control in (self.previous,self.next,self.page_label):control.setVisible(pages>1)
        self.footer.setVisible(pages>1 or bool(self.message.text()))

    def search(self,page=0):
        self.search_timer.stop();self.initialized=True
        text=self.query.text().strip()
        query=(text,self.game.text().strip(),self.loader.currentData() if self.loader.isEnabled() else '',self.target_vid,self.category.currentData() or '',self.sort.currentData() or 'relevance')
        if query!=self.last_search:page=0
        if self.search_job:self.search_job.cancel_job()
        page=max(0,page);self.request_id+=1;request=self.request_id;self.loading=True;self.go.setEnabled(False);self.message.setText('正在搜索…');self.update_paging()
        def done(data):
            if not isValid(self) or request!=self.request_id:return
            self.search_job=None;self.loading=False;self.go.setEnabled(True);self.last_search=query;self.page_number=page
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
            if not isValid(self) or request!=self.request_id:return
            self.search_job=None;self.loading=False;self.go.setEnabled(True);self.message.setText('搜索失败，点击搜索重试');self.message.setToolTip(str(error));self.update_paging()
        from ..catalog import search
        self.query.setToolTip('搜索：'+search_terms(self.kind,text) if search_terms(self.kind,text)!=text else '支持名称、关键词和常用中文别名；按回车搜索')
        self.search_job=self.launcher.tasks.submit(lambda job:search(self.repo.downloader,self.kind,*query[:3],limit=self.PAGE_SIZE,offset=page*self.PAGE_SIZE,category=query[4],sort=query[5]),done,failed,downloader=self.repo.downloader)
