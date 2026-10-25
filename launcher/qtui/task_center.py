"""Live, cancellable task history; retries are explicit in-memory safe recipes."""
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QSplitter
from .widgets import column,row,label,button,TaskDialog


class TaskCenter(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;body=column(self,0,12);heading=row();heading.addWidget(label('下载任务','heading'),1)
        heading.addWidget(button('清除已结束记录',self.clear));body.addLayout(heading)
        split=QSplitter(Qt.Orientation.Vertical);body.addWidget(split,1)
        self.tree=QTreeWidget();self.tree.setRootIsDecorated(False);self.tree.setHeaderLabels(['任务','状态','进度 / 已接收','时间']);self.tree.setColumnWidth(0,250);self.tree.setColumnWidth(1,90);self.tree.setColumnWidth(2,180);split.addWidget(self.tree)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);split.addWidget(self.detail);split.setSizes([420,150])
        actions=row();self.cancel_button=button('取消任务',self.cancel);actions.addWidget(self.cancel_button)
        self.retry_button=button('重新尝试',self.retry,'soft','refresh');actions.addWidget(self.retry_button);actions.addStretch();body.addLayout(actions)
        self.tree.currentItemChanged.connect(lambda *_:self.selection())
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()

    def current(self):
        node=self.tree.currentItem();key=node.data(0,Qt.ItemDataRole.UserRole) if node else None
        return next((v for v in self.owner.task_history.items if v['id']==key),None)

    def refresh(self):
        if not self.isVisible() and self.tree.topLevelItemCount():return
        current=self.current();key=current['id'] if current else None;scroll=self.tree.verticalScrollBar().value();self.tree.blockSignals(True);self.tree.clear()
        names={'running':'进行中','cancelling':'正在取消','complete':'已完成','failed':'失败','cancelled':'已取消','interrupted':'已中断'}
        for item in reversed(self.owner.task_history.items):
            amount=' · '.join(v for v in (item.get('progress'),TaskDialog.byte_text(item.get('bytes',0))) if v)
            node=QTreeWidgetItem([item['title'],names.get(item['state'],item['state']),amount,time.strftime('%m-%d %H:%M',time.localtime(item['started']))]);node.setData(0,Qt.ItemDataRole.UserRole,item['id']);self.tree.addTopLevelItem(node)
            for c in range(4):node.setToolTip(c,node.text(c))
            if item['id']==key:self.tree.setCurrentItem(node)
        if not self.tree.currentItem() and self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.verticalScrollBar().setValue(scroll);self.tree.blockSignals(False);self.selection()

    def selection(self):
        item=self.current();history=self.owner.task_history;key=item['id'] if item else ''
        self.cancel_button.setEnabled(key in history.live and item['state']=='running' if item else False)
        self.retry_button.setEnabled(bool(item and item['state'] in ('failed','cancelled') and key in history.retries and not self.owner.mutating))
        text='' if not item else '\n'.join([item['title'],'游戏目录：'+item['library'],'实例：'+(item['instance'] or '—'),item.get('detail','')])
        if item and item['state'] in ('failed','cancelled','interrupted') and key not in history.retries:text+='\n此记录不能自动重试，请返回原页面重新发起操作。'
        if self.detail.toPlainText()!=text:self.detail.setPlainText(text)

    def cancel(self):
        item=self.current()
        if item and item['id'] in self.owner.task_history.live:
            self.owner.task_history.live[item['id']].cancel_job();item['state']='cancelling';self.refresh()

    def select_task(self,key):
        self.refresh()
        for i in range(self.tree.topLevelItemCount()):
            node=self.tree.topLevelItem(i)
            if node.data(0,Qt.ItemDataRole.UserRole)==key:self.tree.setCurrentItem(node);self.tree.scrollToItem(node);break

    def retry(self):
        item=self.current();recipe=self.owner.task_history.retries.get(item['id']) if item else None
        if recipe and not self.owner.mutating:recipe()

    def clear(self):self.owner.task_history.clear_finished();self.refresh()
