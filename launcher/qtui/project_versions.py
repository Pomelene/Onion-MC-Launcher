"""Select an explicit compatible catalog release inside the main window."""
from .i18n import message,tr
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE,META_ROLE
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QTreeWidgetItem,QWidget,QPlainTextEdit
from .widgets import column,row,label,button,clear,Card,ContentCheck,Page
from ..catalog import pick_version,versions


class ProjectVersions(QDialog):
    def __init__(self,window,project_id,title,kind,game,loader,vid,install_callback=None):
        super().__init__(window);self.launcher=window;self.project_id=project_id;self.kind=kind;self.game=game;self.loader=loader;self.vid=vid;self.entries=[];self.active=True;self.install_callback=install_callback
        self.repo=window.repo
        self.fetch_job=None
        self.dependency_job=None
        self.dependency_request=0
        self.reviewed=None
        self.navigation_title=title
        self.setWindowTitle(tr('选择版本 · ')+title);body=column(self,24,12)
        context=' · '.join(value for value in (window.instances.display_name(vid) if vid else tr('新建实例'),game,loader) if value)
        body.addWidget(label(context,'muted',True))
        filter_bar=row();self.compatible=ContentCheck();self.compatible.setAccessibleName(tr('仅显示兼容版本'));self.compatible.setChecked(True);filter_bar.addWidget(self.compatible);filter_bar.addWidget(label(tr('仅兼容版本'),'muted'));filter_bar.addStretch()
        self.refresh_button=button('',self.fetch,glyph='refresh');self.refresh_button.setToolTip(tr('刷新版本'));self.refresh_button.setAccessibleName(tr('刷新版本'));filter_bar.addWidget(self.refresh_button);body.addLayout(filter_bar)
        self.tree=QTreeWidget();self.tree.setColumnCount(1);self.tree.setHeaderHidden(True);body.addWidget(self.tree,1)
        self.changelog=QPlainTextEdit();self.changelog.setReadOnly(True);self.changelog.setMaximumHeight(160);self.changelog.hide();body.addWidget(self.changelog)
        self.dependencies=Card(tr('必需前置模组'))
        self.dependency_list=Page()
        self.dependency_list.setMaximumHeight(150)
        self.dependencies.body.addWidget(self.dependency_list)
        self.dependencies.hide()
        body.addWidget(self.dependencies)
        actions=row();self.status=label(tr('正在获取版本列表…'),'muted',True);actions.addWidget(self.status,1)
        self.changelog_button=button(tr('更新日志'),self.toggle_changelog);self.changelog_button.hide();actions.addWidget(self.changelog_button)
        self.install_button=button(tr('安装'),self.install,'primary','download');self.install_button.setEnabled(False);actions.addWidget(self.install_button);body.addLayout(actions)
        self.compatible.toggled.connect(self.render);self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_:self.install() if self.reviewed is None else None)
        self.finished.connect(self.close_fetch);self.loading=False;QTimer.singleShot(0,self.fetch)

    def close_fetch(self,*args):
        self.active=False
        if self.fetch_job:self.fetch_job.cancel_job()
        self.reset_dependencies()

    def reset_dependencies(self):
        self.dependency_request+=1
        if self.dependency_job:self.dependency_job.cancel_job()
        self.dependency_job=None
        self.reviewed=None
        self.dependencies.hide()
        self.install_button.setText(tr('安装'))

    def selection_changed(self,*args):
        self.reset_dependencies()
        if not self.loading:self.status.clear()
        self.update_selection()

    def fetch(self):
        if not self.active or self.loading:return
        self.reset_dependencies()
        self.loading=True;self.refresh_button.setEnabled(False);self.update_selection();self.status.setText(tr('正在获取版本列表…'))
        def done(entries):
            self.fetch_job=None
            self.loading=False
            if not self.active:return
            self.refresh_button.setEnabled(True)
            self.entries=sorted(entries,key=lambda v:v.get('date_published',''),reverse=True);self.render()
        def failed(error):
            self.fetch_job=None
            self.loading=False
            if self.active:
                self.refresh_button.setEnabled(True);self.update_selection();self.status.setText(tr('获取失败：')+str(error)+tr('；可点击刷新重试。'))
        key=self.launcher.config_obj.get('curseforge_api_key')
        self.fetch_job=self.launcher.tasks.submit(
            lambda job:versions(self.repo.downloader,self.project_id,key),done,failed,downloader=self.repo.downloader)

    def render(self,*args):
        current=self.tree.currentItem();selected_id=current.data(0,Qt.ItemDataRole.UserRole) if current else None
        self.tree.clear();first=None;stable=None;selected=None
        for version in self.entries:
            compatible=bool(pick_version([version],self.game,self.loader))
            if self.compatible.isChecked() and not compatible:continue
            files=version.get('files') or [];primary=next((f for f in files if f.get('primary')),files[0] if files else {})
            channel={'release':tr('正式版'),'beta':tr('测试版'),'alpha':tr('预览版')}.get(version.get('version_type'),'')
            context=', '.join(version.get('game_versions') or [])+' / '+', '.join(version.get('loaders') or [])
            detail=' · '.join(v for v in (channel,version.get('date_published','')[:10],context.strip(' /') if not self.compatible.isChecked() else '') if v)
            if not compatible:detail+=tr(' · 不兼容')
            item=QTreeWidgetItem([version.get('version_number') or version.get('name') or '']);item.setData(0,DETAIL_ROLE,context.strip(' /') if not self.compatible.isChecked() else None);item.setData(0,META_ROLE,' · '.join(v for v in (channel,version.get('date_published','')[:10]) if v))
            item.setData(0,Qt.ItemDataRole.UserRole,version.get('id'));item.setData(0,Qt.ItemDataRole.UserRole+1,compatible and bool(files))
            item.setToolTip(0,item.text(0)+'\n'+detail+'\n'+context+'\n'+primary.get('filename',''))
            if not compatible:item.setToolTip(0,tr('不匹配当前目标，无法安装到此实例'))
            elif not files:item.setToolTip(0,tr('此版本未提供可下载文件'))
            self.tree.addTopLevelItem(item)
            if version.get('id')==selected_id:selected=item
            if first is None and compatible and files:first=item
            if stable is None and compatible and files and version.get('version_type')=='release':stable=item
        preferred=selected if selected is not None else stable if stable is not None else first
        if preferred is not None:self.tree.setCurrentItem(preferred)
        count=self.tree.topLevelItemCount()
        self.status.setText('' if count else tr('没有兼容版本'));self.update_selection()

    def update_selection(self):
        item=self.tree.currentItem();self.install_button.setEnabled(bool(not self.loading and not self.dependency_job and item and item.data(0,Qt.ItemDataRole.UserRole+1)))
        identifier=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        entry=next((v for v in self.entries if v.get('id')==identifier),{})
        unavailable=tr('此版本未提供可下载文件')
        if not self.loading and self.status.text() in ('',unavailable):
            self.status.setText(unavailable if item and entry and not entry.get('files') else '')
        text=entry.get('changelog') or ''
        self.changelog.setPlainText(text[:50000] if isinstance(text,str) else '')
        self.changelog_button.setVisible(bool(text))
        if not text:self.changelog.hide()

    def toggle_changelog(self):
        self.changelog.setVisible(self.changelog.isHidden())

    def install(self):
        if self.loading or self.dependency_job or not self.active:return
        item=self.tree.currentItem()
        if not item or not item.data(0,Qt.ItemDataRole.UserRole+1):return
        release=item.data(0,Qt.ItemDataRole.UserRole)
        if self.launcher.repo is not self.repo:return
        entry=next((v for v in self.entries if v.get('id')==release),None)
        if entry is None:return
        if self.install_callback:
            started=self.install_callback(release)
        elif self.kind=='mod' and self.reviewed is None and (entry.get('dependencies') or entry.get('cf_dependencies')):
            self.review_dependencies(entry)
            return
        else:
            started=self.start_install(entry, self.reviewed)
        if started:self.accept()

    def start_install(self,entry,plan=None):
        return self.launcher.install_project(
            self.project_id,self.kind,self.game,self.loader,version_id=self.vid,
            release_id=entry['id'],release_entry=entry,reviewed_plan=plan)

    def review_dependencies(self,entry):
        from ..mod_updates import prepare_catalog_install
        request=self.dependency_request
        self.status.setText(tr('正在检查前置模组…'))
        self.install_button.setEnabled(False)
        key=self.launcher.config_obj.get('curseforge_api_key')

        def done(plan):
            if not self.active or request!=self.dependency_request:return
            self.dependency_job=None
            self.status.clear()
            if not any(action!='保留' for _,action in plan['dependencies']):
                if self.start_install(entry,plan):self.accept()
                else:self.update_selection()
                return
            self.reviewed=plan
            clear(self.dependency_list.body)
            for name,action in plan['dependencies']:
                line=row()
                line.addWidget(label(name,wrap=True),1)
                line.addWidget(label(tr({'保留':'已安装','更新':'需要更新','安装':'需要安装'}[action]),'muted'))
                self.dependency_list.body.addLayout(line)
            self.dependencies.show()
            self.install_button.setText(tr('安装模组及前置'))
            self.update_selection()

        def failed(error):
            if not self.active or request!=self.dependency_request:return
            self.dependency_job=None
            self.status.setText(message(str(error)))
            self.install_button.setText(tr('重试'))
            self.update_selection()

        self.dependency_job=self.launcher.tasks.submit(
            lambda job:prepare_catalog_install(self.repo,self.vid,self.project_id,entry,key,job),
            done,failed,downloader=self.repo.downloader)
