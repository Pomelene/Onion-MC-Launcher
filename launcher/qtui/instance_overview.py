"""All saved folders in one instance list; never identifies instances by name alone."""
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QLineEdit,QTreeWidgetItem,QInputDialog,QCheckBox,QHeaderView
from .widgets import column,row,label,button,favorite_button,icon,icon_button,menu_button
from .choices import ChoiceComboBox
from ..instance import InstanceStore


class InstanceOverview(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.navigation_title='实例总览';self.setWindowTitle(self.navigation_title);self.rows=[];self.active=True;self.loading=False
        self.finished.connect(lambda _:setattr(self,'active',False));body=column(self,24,12)
        filters=row();self.query=QLineEdit();self.query.setPlaceholderText('搜索实例、目录或标签');self.query.setClearButtonEnabled(True);filters.addWidget(self.query,1)
        self.only_favorites=QCheckBox('仅收藏');filters.addWidget(self.only_favorites);self.tags_filter=ChoiceComboBox();self.tags_filter.addItem('全部标签','');self.tags_filter.currentIndexChanged.connect(self.render);filters.addWidget(self.tags_filter);self.reload_button=icon_button('刷新',self.fetch,'refresh');filters.addWidget(self.reload_button);body.addLayout(filters)
        self.tree=QTreeWidget();self.tree.entities(1);body.addWidget(self.tree,1)
        self.status=label('正在扫描…','muted',True);body.addWidget(self.status)
        actions=row();self.more=menu_button(lambda:[('编辑标签',self.tags),('管理实例',lambda:self.use('instance'))]);actions.addWidget(self.more);actions.addStretch()
        self.use_button=button('使用',lambda:self.use('home'),'primary');actions.addWidget(self.use_button);body.addLayout(actions)
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
            self.status.setText('不可用目录：'+'、'.join(missing) if missing else '');self.status.setVisible(bool(missing));self.render()
        def failed(error):
            if self.active:self.loading=False;self.reload_button.setEnabled(True);self.status.setText(str(error));self.status.show()
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
            node=QTreeWidgetItem([item['name'],'']);node.setData(0,DETAIL_ROLE,' · '.join(v for v in (item['game'],item['loader'],item['library'],', '.join(item['tags'])) if v));node.setData(0,Qt.ItemDataRole.UserRole,item['key']);self.tree.addTopLevelItem(node)
            self.tree.setItemWidget(node,1,favorite_button(item['favorite'],lambda checked,entry=item:self.set_favorite(entry,checked)));node.setToolTip(0,item['root']+'\n'+item['id'])
            if item['key']==key:self.tree.setCurrentItem(node)
        if not self.tree.currentItem() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.selection()

    def selection(self):
        selected=self.current();enabled=selected is not None
        for control in (self.more,self.use_button):control.setEnabled(enabled)

    def populate_tags(self):
        current=self.tags_filter.currentData();self.tags_filter.blockSignals(True);self.tags_filter.clear();self.tags_filter.addItem('全部标签','')
        for tag in sorted({tag for entry in self.rows for tag in entry['tags']},key=str.casefold):self.tags_filter.addItem(tag,tag)
        self.tags_filter.setCurrentIndex(max(0,self.tags_filter.findData(current)));self.tags_filter.blockSignals(False);self.tags_filter.setVisible(self.tags_filter.count()>1)

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
