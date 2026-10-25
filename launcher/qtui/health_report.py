"""Readable local preflight and evidence-based crash clues, embedded in the shell."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QApplication
from .widgets import column,row,label,button


class HealthReport(QDialog):
    def __init__(self,owner,vid,crash=False):
        super().__init__(owner);self.owner=owner;self.repo=owner.repo;self.vid=vid;self.crash=crash;self.active=True;self.loading=False;self.job=None;self.report=''
        self.navigation_title=('崩溃诊断' if crash else '启动前环境体检')+' · '+owner.instances.display_name(vid);self.setWindowTitle(self.navigation_title)
        self.finished.connect(self.closed);body=column(self,24,12);body.addWidget(label(self.navigation_title,'heading'))
        body.addWidget(label('诊断依据本地日志和规则匹配，不代表已确认根因。' if crash else '本地检查不会登录账户、下载资源或启动游戏。','muted',True))
        self.tree=QTreeWidget();self.tree.setRootIsDecorated(False);self.tree.setHeaderLabels(['项目','来源 / 级别']);self.tree.setColumnWidth(0,430);body.addWidget(self.tree,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);body.addWidget(self.details,1)
        actions=row();self.refresh_button=button('重新检查',self.fetch,glyph='refresh');actions.addWidget(self.refresh_button)
        actions.addWidget(button('模组依赖检查',self.mods));actions.addStretch();actions.addWidget(button('复制报告',self.copy,glyph='copy'));actions.addWidget(button('返回',self.reject));body.addLayout(actions)
        self.tree.currentItemChanged.connect(self.selection);QTimer.singleShot(0,self.fetch)

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
            return inspect(self.repo,self.vid,settings)
        def done(items):
            if not self.active:return
            self.loading=False;self.refresh_button.setEnabled(True);self.tree.clear();blocks=[]
            for item in items:
                if self.crash:title=item['title'];source=item.get('source','');detail='建议：'+item['advice']+'\n\n证据：'+(item['evidence'] or '未找到匹配证据')
                else:title=item.message;source={'error':'需处理','warning':'待核对','info':'提示'}.get(item.severity,item.severity);detail=title+('\n'+item.path if item.path else '')
                node=QTreeWidgetItem([title,source]);node.setData(0,Qt.ItemDataRole.UserRole,detail);self.tree.addTopLevelItem(node);node.setToolTip(0,title)
                blocks.append(title+'\n'+source+'\n'+detail)
            self.report=self.navigation_title+'\n\n'+'\n\n'.join(blocks)
            if self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
            else:self.details.setPlainText('未发现支持范围内的环境问题。')
        def failed(error):
            if self.active:self.loading=False;self.refresh_button.setEnabled(True);self.details.setPlainText(str(error))
        self.job=self.owner.tasks.submit(work,done,failed)

    def selection(self,*args):
        node=self.tree.currentItem();self.details.setPlainText(node.data(0,Qt.ItemDataRole.UserRole) if node else '')

    def copy(self):
        from ..crash import redact
        QApplication.clipboard().setText(redact(self.report))

    def mods(self):self.accept();self.owner.open_mod_manager(self.vid)
