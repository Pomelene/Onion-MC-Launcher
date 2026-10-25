"""All saved folders in one instance list; never identifies instances by name alone."""
from .lists import FlatTreeWidget as QTreeWidget

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QLineEdit,QTreeWidgetItem,QInputDialog,QCheckBox,QHeaderView
from .widgets import column,row,label,button,favorite_button,icon
from .choices import ChoiceComboBox
from ..instance import InstanceStore


class InstanceOverview(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.navigation_title='实例总览';self.setWindowTitle(self.navigation_title);self.rows=[];self.active=True;self.loading=False
        self.finished.connect(lambda _:setattr(self,'active',False));body=column(self,24,12)
        filters=row();self.query=QLineEdit();self.query.setPlaceholderText('搜索实例、目录或标签');self.query.setClearButtonEnabled(True);filters.addWidget(self.query,1)
        self.only_favorites=QCheckBox('仅收藏');filters.addWidget(self.only_favorites);self.tags_filter=ChoiceComboBox();self.tags_filter.addItem('全部标签','');self.tags_filter.currentIndexChanged.connect(self.render);filters.addWidget(self.tags_filter);self.reload_button=button('刷新',self.fetch,glyph='refresh');filters.addWidget(self.reload_button);body.addLayout(filters)
        self.tree=QTreeWidget();self.tree.setRootIsDecorated(False);self.tree.setHeaderLabels(['实例','游戏 / 加载器','所属文件夹','标签','收藏']);self.tree.setColumnWidth(1,140);self.tree.setColumnWidth(2,160);self.tree.setColumnWidth(3,100);self.tree.setColumnWidth(4,48);self.tree.header().setStretchLastSection(False);self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);body.addWidget(self.tree,1)
        self.status=label('正在扫描…','muted',True);body.addWidget(self.status)
        actions=row();self.favorite_button=button('收藏 / 取消收藏',self.favorite,glyph='star');actions.addWidget(self.favorite_button);self.tags_button=button('编辑标签',self.tags);actions.addWidget(self.tags_button);actions.addStretch()
        self.manage_button=button('管理',lambda:self.use('instance'));actions.addWidget(self.manage_button);self.use_button=button('选择并返回首页',lambda:self.use('home'),'primary');actions.addWidget(self.use_button);body.addLayout(actions)
        self.query.textChanged.connect(self.render);self.only_favorites.toggled.connect(self.render);self.tree.currentItemChanged.connect(lambda *_:self.selection());self.tree.itemDoubleClicked.connect(lambda *_:self.use('home'))
        self.selection();QTimer.singleShot(0,self.fetch)

    def fetch(self):
        if not self.active or self.loading:return
        self.loading=True;self.reload_button.setEnabled(False)
        entries=self.owner.game_libraries.entries();path=self.owner.instances.path;legacy=self.owner.config_obj.get('library_legacy_root')
        def work(job):
            from ..instance_library import collect
            return collect(entries,path,legacy,job.cancel)
        def done(result):
            if not self.active:return
            self.loading=False;self.reload_button.setEnabled(True);self.rows,missing=result;self.populate_tags()
            self.status.setText(f'{len(self.rows)} 个实例'+('；不可用目录：'+'、'.join(missing) if missing else ''));self.render()
        def failed(error):
            if self.active:self.loading=False;self.reload_button.setEnabled(True);self.status.setText(str(error))
        self.owner.tasks.submit(work,done,failed)

    def current(self):
        item=self.tree.currentItem();key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        return next((v for v in self.rows if v['key']==key),None)

    def render(self,*args):
        current=self.current();key=current['key'] if current else None;self.tree.clear();query=self.query.text().strip().casefold()
        for item in sorted(self.rows,key=lambda r:(not r['favorite'],r['name'].casefold(),r['root'].casefold(),r['id'])):
            if self.only_favorites.isChecked() and not item['favorite']:continue
            if self.tags_filter.currentData() and self.tags_filter.currentData() not in item['tags']:continue
            if query not in ' '.join([item['name'],item['id'],item['library'],item['root'],*item['tags']]).casefold():continue
            node=QTreeWidgetItem([item['name'],item['game']+' · '+item['loader'],item['library'],', '.join(item['tags']),'']);node.setData(0,Qt.ItemDataRole.UserRole,item['key']);self.tree.addTopLevelItem(node)
            self.tree.setItemWidget(node,4,favorite_button(item['favorite'],lambda checked,entry=item:self.set_favorite(entry,checked)))
            for c in range(4):node.setToolTip(c,node.text(c))
            node.setToolTip(2,item['root'])
            if item['key']==key:self.tree.setCurrentItem(node)
        if not self.tree.currentItem() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.selection()

    def selection(self):
        selected=self.current();enabled=selected is not None
        for control in (self.favorite_button,self.tags_button,self.manage_button,self.use_button):control.setEnabled(enabled)
        glyph='star-filled' if selected and selected['favorite'] else 'star'
        self.favorite_button.setProperty('onionGlyph',glyph);self.favorite_button.setIcon(icon(glyph));self.favorite_button.setText('取消收藏' if selected and selected['favorite'] else '收藏实例')

    def populate_tags(self):
        current=self.tags_filter.currentData();self.tags_filter.blockSignals(True);self.tags_filter.clear();self.tags_filter.addItem('全部标签','')
        for tag in sorted({tag for entry in self.rows for tag in entry['tags']},key=str.casefold):self.tags_filter.addItem(tag,tag)
        self.tags_filter.setCurrentIndex(max(0,self.tags_filter.findData(current)));self.tags_filter.blockSignals(False)

    def store(self,item):return InstanceStore(self.owner.instances.path,item['root'],self.owner.config_obj.get('library_legacy_root'))

    def favorite(self):
        item=self.current()
        if not item:return
        self.set_favorite(item,not item['favorite'])

    def set_favorite(self,item,value):
        try:
            meta=self.store(item).update(item['id'],favorite=value);item['favorite']=meta.favorite;self.owner.instances.load();self.render()
        except Exception as error:self.owner.error(error)

    def tags(self):
        item=self.current()
        if not item:return
        value,ok=QInputDialog.getText(self,'实例标签','多个标签用逗号分隔',text=', '.join(item['tags']))
        if ok:
            try:
                meta=self.store(item).update(item['id'],tags=value);item['tags']=meta.tags;self.owner.instances.load();self.populate_tags();self.render()
            except Exception as error:self.owner.error(error)

    def use(self,page):
        item=self.current()
        if item and self.owner.select_library_instance(item['root'],item['id'],page):self.accept()
