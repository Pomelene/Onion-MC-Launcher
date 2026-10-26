"""Readable local preflight and evidence-based crash clues, embedded in the shell."""
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE,META_ROLE

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidgetItem,QPlainTextEdit,QApplication
from .widgets import column,row,label,button,icon_button


class HealthReport(QDialog):
    def __init__(self,owner,vid,crash=False):
        super().__init__(owner);self.owner=owner;self.repo=owner.repo;self.vid=vid;self.crash=crash;self.active=True;self.loading=False;self.job=None;self.report=''
        self.navigation_title=('崩溃诊断' if crash else '启动前环境体检')+' · '+owner.instances.display_name(vid);self.setWindowTitle(self.navigation_title)
        self.finished.connect(self.closed);body=column(self,20,10)
        actions=row();actions.addStretch();self.refresh_button=icon_button('重新检查',self.fetch,'refresh');actions.addWidget(self.refresh_button)
        actions.addWidget(icon_button('复制报告',self.copy,'copy'));actions.addWidget(icon_button('查看详情',lambda:self.details.setVisible(self.details.isHidden()),'info'));body.addLayout(actions)
        self.tree=QTreeWidget();self.tree.entities();body.addWidget(self.tree,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(180);self.details.hide();body.addWidget(self.details)
        self.tree.currentItemChanged.connect(self.selection);self.tree.itemDoubleClicked.connect(lambda *_:self.details.setVisible(self.details.isHidden()));QTimer.singleShot(0,self.fetch)

    def closed(self,*args):
        self.active=False
        if self.job:self.job.cancel.set()

    def fetch(self):
        if not self.active or self.loading:return
        self.loading=True;self.refresh_button.setEnabled(False)
        settings=self.owner.version_settings.resolve(self.vid,self.owner.config_obj)
        def work(job):
            if self.crash:
                from ..crash import reports
                return reports(self.repo.run_dir(self.vid))
            from ..preflight import inspect
            return inspect(self.repo,self.vid,settings,cancel=job.cancel)
        def done(items):
            if not self.active:return
            self.loading=False;self.refresh_button.setEnabled(True);self.tree.clear();blocks=[]
            for item in items:
                if self.crash:title=item['title'];source=item.get('source','');detail='建议：'+item['advice']+'\n\n证据：'+(item['evidence'] or '未找到匹配证据')
                else:title=item.message;source={'error':'需处理','warning':'待核对','info':'提示'}.get(item.severity,item.severity);detail=title+('\n'+item.path if item.path else '')
                node=QTreeWidgetItem([title]);node.setData(0,META_ROLE,source);node.setData(0,Qt.ItemDataRole.UserRole,detail);self.tree.addTopLevelItem(node);node.setToolTip(0,detail)
                blocks.append(title+'\n'+source+'\n'+detail)
            self.report=self.navigation_title+'\n\n'+'\n\n'.join(blocks)
            if self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
            else:self.details.setPlainText('未发现问题');self.details.show()
        def failed(error):
            if self.active:self.loading=False;self.refresh_button.setEnabled(True);self.details.setPlainText(str(error));self.details.show()
        self.job=self.owner.tasks.submit(work,done,failed)

    def selection(self,*args):
        node=self.tree.currentItem();self.details.setPlainText(node.data(0,Qt.ItemDataRole.UserRole) if node else '')

    def copy(self):
        from ..crash import redact
        QApplication.clipboard().setText(redact(self.report))
