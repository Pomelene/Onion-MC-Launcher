"""Quiet task list, stable live rows and details shown only on request."""
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QTreeWidgetItem,QPlainTextEdit
from .lists import FlatTreeWidget,DETAIL_ROLE,META_ROLE
from .widgets import column,row,button,TaskDialog,icon_button,menu_button


class TaskCenter(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.nodes={};body=column(self,0,8)
        toolbar=row();toolbar.addStretch()
        self.cancel_button=button('取消',self.cancel);toolbar.addWidget(self.cancel_button)
        self.retry_button=button('重试',self.retry,glyph='refresh');toolbar.addWidget(self.retry_button)
        self.details_button=icon_button('任务详情',self.toggle_details,'info');toolbar.addWidget(self.details_button)
        toolbar.addWidget(menu_button(lambda:[('清除已结束记录',self.clear)]));body.addLayout(toolbar)
        self.tree=FlatTreeWidget();self.tree.entities();body.addWidget(self.tree,1)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);self.detail.hide();body.addWidget(self.detail)
        self.tree.currentItemChanged.connect(lambda *_:self.selection());self.tree.itemDoubleClicked.connect(lambda *_:self.toggle_details())
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()

    def current(self):
        node=self.tree.currentItem();key=node.data(0,Qt.ItemDataRole.UserRole) if node else None
        return next((v for v in self.owner.task_history.items if v['id']==key),None)

    def refresh(self):
        if not self.isVisible() and self.tree.topLevelItemCount():return
        names={'running':'进行中','cancelling':'正在取消','complete':'已完成','failed':'失败','cancelled':'已取消','interrupted':'已中断'}
        records=list(reversed(self.owner.task_history.items));keys={i['id'] for i in records}
        self.tree.blockSignals(True)
        for key in list(self.nodes):
            if key not in keys:self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(self.nodes.pop(key)))
        for position,item in enumerate(records):
            key=item['id'];node=self.nodes.get(key)
            if node is None:
                node=QTreeWidgetItem([item['title']]);node.setData(0,Qt.ItemDataRole.UserRole,key);self.nodes[key]=node;self.tree.insertTopLevelItem(position,node)
            detail=' · '.join(v for v in (names.get(item['state'],item['state']),item.get('progress'),TaskDialog.byte_text(item['bytes']) if item.get('bytes') else '') if v)
            values=((Qt.ItemDataRole.DisplayRole,item['title']),(DETAIL_ROLE,detail),(META_ROLE,time.strftime('%m-%d %H:%M',time.localtime(item['started']))))
            for role,value in values:
                if node.data(0,role)!=value:node.setData(0,role,value)
            node.setToolTip(0,item.get('detail') or item['title'])
        if not self.tree.currentItem() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.blockSignals(False);self.selection()

    def selection(self):
        item=self.current();history=self.owner.task_history;key=item['id'] if item else ''
        self.cancel_button.setVisible(bool(item and key in history.live and item['state']=='running'))
        self.retry_button.setVisible(bool(item and item['state'] in ('failed','cancelled') and key in history.retries))
        self.retry_button.setEnabled(not self.owner.mutating);self.details_button.setEnabled(bool(item))
        text='' if not item else '\n'.join(v for v in (item.get('instance'),item.get('library'),item.get('detail')) if v)
        if self.detail.toPlainText()!=text:self.detail.setPlainText(text)
        if not item:self.detail.hide()

    def toggle_details(self):
        if self.current():self.detail.setVisible(self.detail.isHidden())

    def cancel(self):
        item=self.current()
        if item and item['id'] in self.owner.task_history.live:
            self.owner.task_history.live[item['id']].cancel_job();item['state']='cancelling';self.refresh()

    def select_task(self,key):
        self.refresh()
        node=self.nodes.get(key)
        if node:self.tree.setCurrentItem(node);self.tree.scrollToItem(node)

    def retry(self):
        item=self.current();recipe=self.owner.task_history.retries.get(item['id']) if item else None
        if recipe and not self.owner.mutating:recipe()

    def clear(self):self.owner.task_history.clear_finished();self.refresh()
