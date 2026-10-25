"""Embedded dependency audit, update selection and explicit shared-dependency preview."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QStackedWidget,QTreeWidget,QTreeWidgetItem,QCheckBox,QPlainTextEdit,QMessageBox
from urllib.parse import quote
from .widgets import column,row,label,button


class ModManager(QDialog):
    def __init__(self,owner,vid,release_id=None,project_id=None):
        super().__init__(owner);self.owner=owner;self.repo=owner.repo;self.vid=vid;self.release_id=release_id;self.project_id=project_id;self.active=True;self.busy=False;self.plan=None
        self.navigation_title='模组检查与更新 · '+owner.instances.display_name(vid);self.setWindowTitle(self.navigation_title)
        self.finished.connect(self.closed);self.read_job=None;body=column(self,24,12)
        body.addWidget(label(owner.instances.display_name(vid),'heading'));self.context_label=label('正在读取运行环境…','muted',True);body.addWidget(self.context_label);body.addWidget(label(str(self.repo.run_dir(vid)/'mods'),'muted',True))
        actions=row();self.audit_button=button('依赖检查',self.check,glyph='search');actions.addWidget(self.audit_button)
        self.updates_button=button('检查模组更新',self.find_updates,glyph='refresh');actions.addWidget(self.updates_button)
        self.preview_versions=QCheckBox('包含测试版更新');actions.addWidget(self.preview_versions);actions.addStretch();body.addLayout(actions)
        nav=row(spacing=6);body.addLayout(nav);self.tabs=QStackedWidget();body.addWidget(self.tabs,1)
        self.issues=self.tree(['级别','检查结果']);self.versions=self.tree(['选择 / 模组','当前版本','可用版本','渠道']);self.proposal=self.tree(['操作 / 项目','版本','文件','依赖来源'])
        self.tab_buttons=[]
        for title,widget in [('依赖检查',self.issues),('更新 / 安装',self.versions),('变更方案',self.proposal)]:
            index=self.tabs.addWidget(widget);control=button(title,lambda w=widget:self.tabs.setCurrentWidget(w),'nav');control.setCheckable(True);nav.addWidget(control);self.tab_buttons.append(control)
        nav.addStretch();self.tabs.currentChanged.connect(lambda index:[b.setChecked(i==index) for i,b in enumerate(self.tab_buttons)]);self.tab_buttons[0].setChecked(True)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(110);self.details.setPlaceholderText('选择项目查看证据、更新内容或依赖来源');body.addWidget(self.details)
        self.optional=QCheckBox('同时包含可选依赖（必需依赖由方案统一分配）');body.addWidget(self.optional)
        self.status=label('','muted',True);body.addWidget(self.status)
        footer=row();self.search_button=button('搜索所选前置',self.search_dependency,'soft','search');footer.addWidget(self.search_button)
        self.undo_button=button('撤销上次变更',self.undo);footer.addWidget(self.undo_button)
        self.recover_button=button('恢复中断变更',self.recover);footer.addWidget(self.recover_button);footer.addStretch();body.addLayout(footer)
        footer=row();footer.addStretch()
        self.plan_button=button('生成依赖方案',self.make_plan,'soft');footer.addWidget(self.plan_button)
        self.apply_button=button('确认安装',self.apply,'primary','download');footer.addWidget(self.apply_button);body.addLayout(footer)
        self.optional.toggled.connect(self.invalidate);self.versions.itemChanged.connect(lambda *_:self.invalidate())
        self.versions.currentItemChanged.connect(self.version_details);self.issues.currentItemChanged.connect(self.issue_details)
        self.proposal.currentItemChanged.connect(lambda *_:self.details.setPlainText(self.proposal.currentItem().toolTip(3) if self.proposal.currentItem() else ''))
        self.enabled();QTimer.singleShot(0,self.load_release if release_id or project_id else self.check)

    @staticmethod
    def tree(headers):
        tree=QTreeWidget();tree.setRootIsDecorated(False);tree.setHeaderLabels(headers);tree.setColumnWidth(0,220)
        return tree

    def closed(self,*args):
        self.active=False
        if self.read_job:self.read_job.cancel.set()

    def context(self):
        from ..modpack import _detect_loader
        rv=self.repo.resolver.resolve(self.vid);game=rv.game_version;loader,version=_detect_loader(self.repo,self.vid)
        settings=self.owner.version_settings.resolve(self.vid,self.owner.config_obj);java=str(rv.java_major or '')
        explicit=settings.get('java_path')
        if explicit:
            from pathlib import Path
            from ..java import probe_java
            selected=probe_java(Path(explicit));java=str(selected.major) if selected else ''
        self.environment={'game':game,'loader':loader,'version':version,'java':java,'automatic':not bool(explicit),'source':rv.game_version_source}
        return game,loader,version

    def enabled(self):
        for control in (self.audit_button,self.updates_button,self.undo_button,self.recover_button,self.optional,self.preview_versions):control.setEnabled(not self.busy)
        self.plan_button.setEnabled(not self.busy and bool(self.roots()))
        self.apply_button.setEnabled(not self.busy and self.plan is not None and any(e['action']!='保留' for e in self.plan['entries']))
        self.search_button.setEnabled(not self.busy and bool(self.issues.currentItem() and self.issues.currentItem().data(0,Qt.ItemDataRole.UserRole)))

    def run_read(self,title,work,done):
        if self.busy or not self.active:return
        self.busy=True;self.status.setText(title);self.enabled()
        def success(value):
            if self.active:
                self.busy=False
                if hasattr(self,'environment'):
                    env=self.environment
                    self.context_label.setText(' · '.join(['Minecraft '+(env['game'] or '版本信息缺失'),(env['loader'] or '原版')+(' '+env['version'] if env['version'] else ''),'Java '+(env['java'] or '未识别')+('（自动选择）' if env['automatic'] else '（指定）')]))
                    self.context_label.setToolTip('游戏版本来源：'+(env['source'] or '未找到客户端版本信息'))
                done(value);self.enabled()
        def failed(error):
            if self.active:self.busy=False;self.status.setText(str(error));self.enabled()
        self.read_job=self.owner.tasks.submit(work,success,failed,lambda value:self.status.setText(value) if self.active and isinstance(value,str) else None,self.repo.downloader)

    def check(self):
        def work(job):
            from ..mod_audit import audit,runtime_modules
            game,loader,version=self.context();return audit(self.repo.run_dir(self.vid)/'mods',game,loader,version,self.environment['java'],runtime_mods=runtime_modules(self.repo,self.vid))
        def done(issues):
            self.issues.clear()
            for issue in issues:
                node=QTreeWidgetItem([{'error':'需处理','warning':'待核对','info':'提示'}.get(issue.severity,issue.severity),issue.message]);node.setData(0,Qt.ItemDataRole.UserRole,issue.dependency if issue.code in ('missing','version') and issue.dependency not in ('java','minecraft','fabricloader','quilt_loader','forge','neoforge') else '')
                node.setToolTip(1,issue.message+'\n'+issue.path);self.issues.addTopLevelItem(node)
            if not issues:self.issues.addTopLevelItem(QTreeWidgetItem(['通过','未发现缺少前置、版本不匹配或重复的顶层模组']))
            self.status.setText(f'{sum(i.severity=="error" for i in issues)} 项需处理，{sum(i.severity=="warning" for i in issues)} 项提示。选择条目查看具体原因。' if issues else '依赖检查通过。')
            self.tabs.setCurrentWidget(self.issues)
        self.run_read('正在读取本地依赖…',work,done)

    def roots(self):
        return [self.versions.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole) for i in range(self.versions.topLevelItemCount()) if self.versions.topLevelItem(i).checkState(0)==Qt.CheckState.Checked]

    def populate(self,entries,unknown):
        self.versions.blockSignals(True);self.versions.clear()
        for entry in entries:
            latest=entry['latest'];current=entry.get('current') or {}
            node=QTreeWidgetItem([entry['path'].name if entry.get('path') else latest.get('name') or latest['project_id'],current.get('version_number','未安装'),latest.get('version_number',''),latest.get('version_type','')])
            node.setData(0,Qt.ItemDataRole.UserRole,latest);node.setCheckState(0,Qt.CheckState.Checked);node.setToolTip(0,node.text(0));self.versions.addTopLevelItem(node)
        self.versions.blockSignals(False);self.invalidate();self.tabs.setCurrentWidget(self.versions)
        self.status.setText(f'{len(entries)} 个可选项目；{len(unknown)} 个文件未能在 Modrinth 确认，不能据此判断是否最新。')
        if unknown:self.details.setPlainText('\n'.join(unknown))

    def find_updates(self):
        allow=self.preview_versions.isChecked()
        def work(job):
            from ..mod_plan import updates
            game,loader,_=self.context();return updates(self.repo.downloader,self.repo.run_dir(self.vid)/'mods',game,loader,job,allow)
        self.run_read('正在识别模组与检查更新…',work,lambda data:self.populate(*data))

    def load_release(self):
        def work(job):
            from ..mods import MODRINTH_API
            from ..catalog import pick_version
            game,loader,_=self.context()
            if self.release_id:version=self.repo.downloader.fetch_json(MODRINTH_API+'/version/'+quote(self.release_id,safe=''))
            else:version=pick_version(self.repo.downloader.fetch_json(MODRINTH_API+'/project/'+quote(self.project_id,safe='')+'/version'),game,loader)
            if not version:raise ValueError('没有兼容版本')
            return [dict(latest=version)],[]
        self.run_read('正在获取所选版本…',work,lambda data:self.populate(*data))

    def invalidate(self,*args):self.plan=None;self.proposal.clear();self.enabled()

    def make_plan(self):
        roots=self.roots();optional=self.optional.isChecked()
        if not roots:return
        def work(job):
            from ..mod_plan import build_plan
            game,loader,_=self.context();return build_plan(self.repo.downloader,self.repo.run_dir(self.vid)/'mods',roots,game,loader,job,optional)
        def done(plan):
            self.plan=plan;self.proposal.clear()
            for entry in plan['entries']:
                node=QTreeWidgetItem([entry['action']+' · '+entry['project'],entry['version'].get('version_number',''),entry['file']['filename'],'、'.join(entry['reasons'])]);self.proposal.addTopLevelItem(node)
                for c in range(4):node.setToolTip(c,node.text(c))
            self.status.setText('请检查全部依赖与目标实例后确认安装。未识别的本地文件不会被自动替换。');self.tabs.setCurrentWidget(self.proposal)
            self.details.setPlainText('目标实例：'+self.vid+'\n目标目录：'+str(self.repo.run_dir(self.vid)/'mods')+'\n'+f'共 {sum(e["action"]!="保留" for e in plan["entries"])} 项文件变更；必需依赖由所选项目共同分配，出现固定版本冲突时不会自动安装。')
        self.run_read('正在合并依赖与校验方案…',work,done)

    def apply(self):
        if self.plan is None or self.busy:return
        count=sum(e['action']!='保留' for e in self.plan['entries'])
        if QMessageBox.question(self,'确认模组变更',f'将为实例 {self.vid} 安装或更新 {count} 个文件。\n旧文件将保留备份，可撤销。\n确认应用当前依赖方案？')!=QMessageBox.StandardButton.Yes:return
        owner,repo,vid,plan=self.owner,self.repo,self.vid,self.plan
        def start():
            if owner.repo is not repo:owner.error('当前游戏目录已切换，请回到目标实例重新生成方案');return
            def work(job):
                from ..mod_plan import apply_plan
                return apply_plan(repo,vid,plan,job)
            def done(value):
                if self.active:self.invalidate();self.check()
                owner.status.setText('模组变更已完成；可在检查页撤销')
            return owner.task('应用模组变更',work,done,retry=start,task_repo=repo,task_instance=vid)
        if start():self.plan=None;self.enabled()

    def undo(self):
        if QMessageBox.question(self,'撤销模组变更','恢复此实例最近一次变更前的模组文件？当前文件已被再次修改时会拒绝恢复。')!=QMessageBox.StandardButton.Yes:return
        repo,vid=self.repo,self.vid
        def work(job):
            from ..mod_plan import undo_last
            return undo_last(repo,vid)
        self.owner.task('撤销模组变更',work,lambda _:self.check() if self.active else None,task_repo=repo,task_instance=vid)

    def recover(self):
        if QMessageBox.question(self,'恢复中断变更','将检查并回退上次被意外中断的模组文件变更；若文件已被修改，会停止恢复。')!=QMessageBox.StandardButton.Yes:return
        repo,vid=self.repo,self.vid
        def work(job):
            from ..mod_plan import recover_interrupted
            return recover_interrupted(repo,vid)
        self.owner.task('恢复中断模组变更',work,lambda _:self.check() if self.active else None,task_repo=repo,task_instance=vid)

    def issue_details(self,*args):
        node=self.issues.currentItem();self.details.setPlainText(node.toolTip(1) if node else '');self.enabled()

    def version_details(self,*args):
        node=self.versions.currentItem();value=node.data(0,Qt.ItemDataRole.UserRole) if node else {}
        self.details.setPlainText((value.get('changelog') or '该版本未提供更新说明')[:20000])

    def search_dependency(self):
        node=self.issues.currentItem();dep=node.data(0,Qt.ItemDataRole.UserRole) if node else ''
        if not dep:return
        if self.owner.repo is not self.repo:self.owner.error('请先切换回目标游戏目录');return
        if not self.owner.set_selected(self.vid,refresh_page=False):return
        self.accept();self.owner.open_content_download('mods');browser=self.owner.download_browser
        browser.query.setText(dep);browser.search(0)
