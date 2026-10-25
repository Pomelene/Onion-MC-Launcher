"""Direct selectable mod updates, with a separate dependency report."""
from urllib.parse import quote
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QStackedWidget,QTreeWidget,QTreeWidgetItem,QCheckBox,QPlainTextEdit,QLineEdit,QHeaderView
from .widgets import column,row,label,button,Page,ContentRow,clear


class ModManager(QDialog):
    def __init__(self,owner,vid,release_id=None,project_id=None,mode='audit'):
        super().__init__(owner)
        self.owner=owner;self.repo=owner.repo;self.vid=vid;self.release_id=release_id;self.project_id=project_id
        self.mode='install' if release_id or project_id else mode
        self.active=True;self.busy=False;self.read_job=None;self.entries=[];self.rows=[];self.unknown=[]
        self.navigation_title={'audit':'模组依赖检查','updates':'模组更新','install':'安装模组'}[self.mode]+' · '+owner.instances.display_name(vid)
        self.setWindowTitle(self.navigation_title);self.finished.connect(self.closed);body=column(self,20,12)
        self.context_label=label('正在读取运行环境…','muted',True)
        self.context_label.setToolTip(str(self.repo.run_dir(vid)/'mods'));body.addWidget(self.context_label)
        toolbar=row();body.addLayout(toolbar)
        self.audit_button=button('重新检查',self.check,glyph='refresh');toolbar.addWidget(self.audit_button)
        self.updates_button=button('重新检查',self.find_updates,glyph='refresh');toolbar.addWidget(self.updates_button)
        self.query=QLineEdit();self.query.setPlaceholderText('筛选模组');self.query.setClearButtonEnabled(True);toolbar.addWidget(self.query,1)
        self.tabs=QStackedWidget();body.addWidget(self.tabs,1)
        self.issues=QTreeWidget();self.issues.setRootIsDecorated(False);self.issues.setHeaderLabels(['状态','检查结果'])
        self.issues.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.issues.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);self.tabs.addWidget(self.issues)
        self.versions=Page();self.versions.body.setSpacing(0);self.tabs.addWidget(self.versions)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(110);self.details.hide();body.addWidget(self.details)
        summary=row();self.status=label('','muted',True);summary.addWidget(self.status,1)
        self.unknown_button=button('',self.show_unknown);self.unknown_button.hide();summary.addWidget(self.unknown_button);body.addLayout(summary)
        footer=row();body.addLayout(footer)
        self.select_all=QCheckBox('全选');self.select_all.setTristate(True);self.select_all.clicked.connect(self.select_everything);footer.addWidget(self.select_all)
        self.preview_versions=QCheckBox('包含测试版');self.preview_versions.toggled.connect(self.find_updates);footer.addWidget(self.preview_versions)
        self.search_button=button('下载缺少的前置',self.search_dependency,glyph='search');footer.addWidget(self.search_button)
        footer.addStretch();self.apply_button=button('更新所选',self.apply,'primary','download');footer.addWidget(self.apply_button)
        self.query.textChanged.connect(self.filter_rows);self.issues.currentItemChanged.connect(self.issue_details)
        self.update_controls();QTimer.singleShot(0,self.load_release if self.mode=='install' else self.find_updates if self.mode=='updates' else self.check)

    def closed(self,*args):
        self.active=False
        if self.read_job:self.read_job.cancel.set()

    def context(self):
        from ..modpack import _detect_loader
        rv=self.repo.resolver.resolve(self.vid);loader,version=_detect_loader(self.repo,self.vid)
        settings=self.owner.version_settings.resolve(self.vid,self.owner.config_obj);java=str(rv.java_major or '')
        explicit=settings.get('java_path')
        if explicit:
            from pathlib import Path
            from ..java import probe_java
            selected=probe_java(Path(explicit));java=str(selected.major) if selected else ''
        self.environment={'game':rv.game_version,'loader':loader,'version':version,'java':java,'automatic':not bool(explicit),'source':rv.game_version_source}
        return rv.game_version,loader,version

    def selected(self):return [entry for entry,check,_ in self.rows if check.isChecked()]

    def update_controls(self):
        audit=self.mode=='audit';count=len(self.selected())
        self.tabs.setCurrentWidget(self.issues if audit else self.versions)
        self.audit_button.setVisible(audit);self.updates_button.setVisible(self.mode=='updates');self.query.setVisible(not audit)
        self.select_all.setVisible(not audit);self.preview_versions.setVisible(self.mode=='updates');self.apply_button.setVisible(not audit)
        for control in (self.audit_button,self.updates_button,self.preview_versions,self.select_all):control.setEnabled(not self.busy)
        for _,check,_ in self.rows:check.setEnabled(not self.busy)
        self.apply_button.setText(('安装所选' if self.mode=='install' else '更新所选')+(f'（{count}）' if count else ''))
        self.apply_button.setEnabled(not self.busy and count>0)
        self.search_button.setVisible(audit and bool(self.issues.currentItem() and self.issues.currentItem().data(0,Qt.ItemDataRole.UserRole)))
        self.search_button.setEnabled(not self.busy)

    def run_read(self,title,work,done):
        if self.busy or not self.active:return
        self.busy=True;self.status.setText(title);self.update_controls()
        def success(value):
            if not self.active:return
            self.busy=False
            if hasattr(self,'environment'):
                env=self.environment;self.context_label.setText(' · '.join(['Minecraft '+(env['game'] or '版本信息缺失'),(env['loader'] or '原版')+(' '+env['version'] if env['version'] else ''),'Java '+(env['java'] or '未识别')+('（自动选择）' if env['automatic'] else '')]))
            done(value);self.update_controls()
        def failed(error):
            if self.active:self.busy=False;self.status.setText(str(error));self.update_controls()
        self.read_job=self.owner.tasks.submit(work,success,failed,lambda value:self.status.setText(value) if self.active and isinstance(value,str) else None,self.repo.downloader)

    def check(self):
        def work(job):
            from ..mod_audit import audit,runtime_modules
            game,loader,version=self.context()
            return audit(self.repo.run_dir(self.vid)/'mods',game,loader,version,self.environment['java'],runtime_mods=runtime_modules(self.repo,self.vid),cancel=job.cancel,progress=lambda n,total:job.emit(f'检查模组 {n}/{total}'))
        def done(issues):
            self.issues.clear()
            for issue in issues:
                node=QTreeWidgetItem([{'error':'需处理','warning':'提示','info':'提示'}.get(issue.severity,issue.severity),issue.message])
                node.setData(0,Qt.ItemDataRole.UserRole,issue.dependency if issue.code in ('missing','version') and issue.dependency not in ('java','minecraft','fabricloader','quilt_loader','forge','neoforge') else '')
                node.setToolTip(1,issue.message+'\n'+issue.path);self.issues.addTopLevelItem(node)
            if not issues:self.issues.addTopLevelItem(QTreeWidgetItem(['通过','未发现依赖问题']))
            self.status.setText(f'{sum(i.severity=="error" for i in issues)} 项需处理，{sum(i.severity=="warning" for i in issues)} 项提示' if issues else '依赖检查通过。')
        self.run_read('正在检查依赖…',work,done)

    @staticmethod
    def decorate(entries):
        from ..mods import read_mod_info
        from .content_icons import read_content_icon
        for entry in entries:
            if entry.get('path'):
                info=read_mod_info(entry['path']);entry['display_name']=info.name;entry['artwork']=read_content_icon(entry['path'])
        entries.sort(key=lambda entry:(entry.get('display_name') or entry['latest'].get('name') or entry['latest']['project_id']).casefold())
        return entries

    def populate(self,entries,unknown):
        self.entries=entries;self.unknown=unknown;self.rows=[];clear(self.versions.body);self.details.hide()
        for entry in entries:
            latest=entry['latest'];current=entry.get('current') or {}
            title=entry.get('display_name') or latest.get('name') or latest['project_id']
            detail=current.get('version_number','未安装')+'  →  '+latest.get('version_number','')
            if latest.get('version_type')!='release':detail+=' · '+{'beta':'测试版','alpha':'开发版'}.get(latest.get('version_type'),'测试版')
            item=ContentRow(title,detail,'package',True,self.selection_changed)
            item.check.setToolTip('选择更新 '+title);item.check.setAccessibleName('选择 '+title)
            item.set_artwork(entry.get('artwork'));item.text.setToolTip(title+'\n'+detail+('\n'+str(entry['path']) if entry.get('path') else ''))
            item.mouseReleaseEvent=lambda event,check=item.check:check.click() if event.button()==Qt.MouseButton.LeftButton else None
            self.versions.body.addWidget(item);self.rows.append((entry,item.check,item))
        if not entries:self.versions.body.addWidget(label('没有找到可用更新' if self.mode=='updates' else '没有可安装的版本','muted'))
        self.unknown_button.setText(f'{len(unknown)} 个未识别');self.unknown_button.setVisible(bool(unknown))
        self.status.setText(f'{len(entries)} 个可更新' if self.mode=='updates' else '')
        self.selection_changed();self.filter_rows()

    def selection_changed(self):
        count=len(self.selected());self.select_all.blockSignals(True)
        self.select_all.setCheckState(Qt.CheckState.Checked if count and count==len(self.rows) else Qt.CheckState.PartiallyChecked if count else Qt.CheckState.Unchecked)
        self.select_all.blockSignals(False);self.update_controls()

    def select_everything(self,checked):
        for _,check,_ in self.rows:check.setChecked(checked)
        self.selection_changed()

    def filter_rows(self,*args):
        query=self.query.text().strip().casefold()
        for entry,_,item in self.rows:item.setVisible(query in (item.text.title+' '+item.text.detail+' '+str(entry.get('path',''))).casefold())

    def show_unknown(self):
        if self.details.isVisible():self.details.hide();return
        self.details.setPlainText('\n'.join(self.unknown));self.details.show()

    def find_updates(self,*args):
        if self.busy:return
        allow=self.preview_versions.isChecked()
        def work(job):
            from ..mod_plan import updates
            game,loader,_=self.context();entries,unknown=updates(self.repo.downloader,self.repo.run_dir(self.vid)/'mods',game,loader,job,allow)
            return self.decorate(entries),unknown
        self.run_read('正在检查更新…',work,lambda data:self.populate(*data))

    def load_release(self):
        def work(job):
            from ..mods import MODRINTH_API
            from ..catalog import pick_version
            game,loader,_=self.context()
            version=self.repo.downloader.fetch_json(MODRINTH_API+'/version/'+quote(self.release_id,safe='')) if self.release_id else pick_version(self.repo.downloader.fetch_json(MODRINTH_API+'/project/'+quote(self.project_id,safe='')+'/version'),game,loader)
            if not version:raise ValueError('没有兼容版本')
            return [dict(latest=version)],[]
        self.run_read('正在获取版本…',work,lambda data:self.populate(*data))

    def apply(self):
        entries=self.selected()
        if self.busy or not entries:return
        owner,repo,vid=self.owner,self.repo,self.vid;install=self.mode=='install'
        def start():
            if owner.repo is not repo:owner.error('游戏目录已切换，请回到原实例重新检查');return
            self.busy=True;self.update_controls()
            def work(job):
                from ..mod_updates import install_selected
                selected=entries
                if install:
                    from ..mod_plan import build_plan
                    game,loader,_=self.context();plan=build_plan(repo.downloader,repo.run_dir(vid)/'mods',[entry['latest'] for entry in entries],game,loader,job)
                    selected=[dict(path=repo.run_dir(vid)/'mods'/e['old'] if e['old'] else None,latest=e['version'],old_sha1=plan['before'].get(e['old'],'')) for e in plan['entries'] if e['action']!='保留']
                return install_selected(repo,vid,selected,job)
            def done(files):
                if self.active:
                    self.busy=False;self.populate([entry for entry in self.entries if entry not in entries],self.unknown)
                    self.status.setText(f'已更新 {len(files)} 个模组' if not install else '安装完成')
                owner.status.setText('模组更新完成' if not install else '模组安装完成')
            task=owner.task('更新模组' if not install else '安装模组',work,done,retry=start,task_repo=repo,task_instance=vid)
            if task:
                original=owner.tasks.jobs[task.key]
                def failed(error):
                    if self.active:self.busy=False;self.status.setText('更新未完成，可重试');self.update_controls()
                    if original[2]:original[2](error)
                owner.tasks.jobs[task.key]=(original[0],original[1],failed,original[3])
            else:self.busy=False;self.update_controls()
            return task
        start()

    def issue_details(self,*args):self.update_controls()

    def search_dependency(self):
        node=self.issues.currentItem();dep=node.data(0,Qt.ItemDataRole.UserRole) if node else ''
        if not dep:return
        if self.owner.repo is not self.repo:self.owner.error('请先切换回目标游戏目录');return
        if not self.owner.set_selected(self.vid,refresh_page=False):return
        self.accept();self.owner.open_content_download('mods');browser=self.owner.download_browser;browser.query.setText(dep);browser.search(0)
