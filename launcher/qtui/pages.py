"""Qt pages delegate filesystem, network and installation work to existing services."""
from .lists import FlatTreeWidget as QTreeWidget

from pathlib import Path
from .choices import ChoiceComboBox,ActionMenu
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QLineEdit,QComboBox,QFormLayout,QCheckBox,QSpinBox,QHeaderView,
    QTabWidget,QFileDialog,QMessageBox,QDialog,QTreeWidgetItem,QMenu)
from .widgets import Page,Card,Empty,HomeCanvas,ContentRow,WelcomeLine,label,button,column,row,clear,icon,favorite_button


class Pages:
    def build_home(self):
        body=self.page('home');canvas=HomeCanvas(self.config_obj.get('background_image') or '',config=self.config_obj)
        self.home_canvas=canvas
        overlay=column(canvas,40,12)
        hero=column(spacing=12)
        self.welcome_large=WelcomeLine(True);self.welcome_small=WelcomeLine()
        hero.addWidget(self.welcome_large);hero.addWidget(self.welcome_small);self.update_home_welcome()
        overlay.addSpacing(44);overlay.addLayout(hero);overlay.addStretch()
        bottom=row(spacing=20);bottom.addStretch()
        from .launch_control import LaunchControl
        start=LaunchControl(self.launch_selected,self.quick_select)
        self.launch_button=start.launch;self.quick_button=start.quick;bottom.addWidget(start)
        overlay.addLayout(bottom);body.addWidget(canvas,1);self.update_selection()

    def update_home_welcome(self,settings=None):
        if not hasattr(self,'welcome_large'):return
        settings=settings if settings is not None else self.config_obj
        custom=settings.get('custom_home_welcome')
        large=(settings.get('home_welcome_large') or '') if custom else ''
        small=(settings.get('home_welcome_small') or '') if custom else ''
        for widget,text in ((self.welcome_large,large),(self.welcome_small,small)):
            widget.setText(text);widget.setVisible(bool(text))

    def open_appearance(self):
        self.navigate('settings');self.open_settings_tab(self.settings_editor.tab_names['外观'])

    def build_instance(self):
        vid=self.selected_version
        if not vid:
            self.logs.setParent(None);self.instance_context='';self.instance_editor=None
            body=self.page('instance');body.setContentsMargins(24,20,24,20)
            body.addWidget(Empty('尚未选择游戏实例','从实例列表选择已有游戏，或前往下载添加版本。','grid','选择实例',lambda:self.navigate('versions')));return
        if self.instance_context!=vid:
            from .workspace import InstanceWorkspace
            self.logs.setParent(None)
            for key in ('mods','worlds','logs'):self.page_seq[key]=self.page_seq.get(key,0)+1
            body=self.page('instance');self.instance_workspace=InstanceWorkspace(self,vid);body.addWidget(self.instance_workspace,1)
            self.instance_context=vid;self.instance_editor=self.instance_workspace.editor
        self.instance_workspace.open_tab(self.instance_tab)

    def build_versions(self):
        body=self.page('versions')
        toolbar=row();query=QLineEdit();self.library_search=query;query.setPlaceholderText('搜索实例');query.setClearButtonEnabled(True);query.setText(getattr(self,'library_query',''));toolbar.addWidget(query,1)
        kinds=ChoiceComboBox();kinds.addItems(['全部类型','原版','Fabric','Forge','NeoForge','Quilt','OptiFine']);kinds.setCurrentIndex(getattr(self,'library_kind',0));toolbar.addWidget(kinds)
        sort=ChoiceComboBox();sort.addItems(['名称排序','最近游玩','游玩时长']);sort.setCurrentIndex(getattr(self,'library_sort',0));toolbar.addWidget(sort)
        kinds.setMaximumWidth(110);sort.setMaximumWidth(125)
        toolbar.addWidget(button('安装',self.install_dialog,'primary','plus'));body.addLayout(toolbar)
        filters=row();favorites=ChoiceComboBox();favorites.addItems(['全部实例','仅收藏']);favorites.setCurrentIndex(int(getattr(self,'library_favorites_only',False)));self.library_favorites=favorites
        tags=ChoiceComboBox();tags.addItem('全部标签','')
        for tag in sorted({tag for vid in self.versions for tag in self.instances.get(vid).tags},key=str.casefold):tags.addItem(tag,tag)
        tags.setCurrentIndex(max(0,tags.findData(getattr(self,'library_tag',''))));self.library_tags=tags
        filters.addWidget(label('筛选','muted'));filters.addWidget(favorites);filters.addWidget(tags);filters.addStretch();body.addLayout(filters)
        library=row();path=label(str(self.repo.game_dir),'muted');path.setMinimumWidth(0)
        from PySide6.QtWidgets import QSizePolicy
        path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);path.setToolTip(str(self.repo.game_dir))
        library.addWidget(path,1);library.addWidget(button('刷新',self.reload_versions,glyph='refresh'));body.addLayout(library)
        tree=QTreeWidget();self.version_tree=tree;tree.setRootIsDecorated(False);tree.setHeaderLabels(['实例名称','游戏版本 / 加载器','分组 / 标签','上次游玩','收藏']);tree.header().setStretchLastSection(False);tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);tree.setColumnWidth(1,210);tree.setColumnWidth(2,110);tree.setColumnWidth(3,140);tree.setColumnWidth(4,48);tree.setMinimumHeight(300);body.addWidget(tree,1)
        summary=label('','muted');body.addWidget(summary)
        def render():
            self.library_query=query.text();self.library_kind=kinds.currentIndex();self.library_sort=sort.currentIndex();tree.clear();text=query.text().strip().lower()
            self.library_favorites_only=bool(favorites.currentIndex());self.library_tag=tags.currentData() or ''
            versions=[v for v in self.versions if (kinds.currentIndex()==0 or self.kinds.get(v)==kinds.currentText()) and text in (v+' '+self.instances.display_name(v)+' '+self.instances.get(v).group+' '+' '.join(self.instances.get(v).tags)).lower()]
            versions=[v for v in versions if (not self.library_favorites_only or self.instances.get(v).favorite) and (not self.library_tag or self.library_tag in self.instances.get(v).tags)]
            versions.sort(key=(lambda v:self.instances.display_name(v).lower()) if sort.currentIndex()==0 else (lambda v:self.instances.get(v).last_played) if sort.currentIndex()==1 else (lambda v:self.instances.get(v).play_seconds),reverse=sort.currentIndex()!=0)
            versions.sort(key=lambda v:not self.instances.get(v).favorite)
            for vid in versions:
                meta=self.instances.get(vid);item=QTreeWidgetItem([meta.display_name,vid+' · '+self.kinds.get(vid,'原版'),' · '.join([meta.group,*meta.tags]),meta.last_played_text(),'']);item.setData(0,Qt.ItemDataRole.UserRole,vid)
                for column in range(tree.columnCount()):item.setToolTip(column,item.text(column))
                tree.addTopLevelItem(item)
                def mark(checked,version=vid):
                    try:self.instances.update(version,favorite=checked)
                    except Exception as error:self.error(error)
                    render()
                tree.setItemWidget(item,4,favorite_button(meta.favorite,mark))
                if vid==self.selected_version:tree.setCurrentItem(item)
            summary.setText(f'{len(versions)} / {len(self.versions)} 个实例')
        tree.setToolTip('单击选择，双击返回首页；右键管理实例')
        def chosen():
            item=tree.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else ''
        def select_home(*args):
            if chosen() and self.set_selected(chosen(),refresh_page=False):self.navigate('home')
        def manage():
            if chosen():self.instance_settings(chosen())
        tree.itemClicked.connect(lambda item,column:self.set_selected(item.data(0,Qt.ItemDataRole.UserRole),refresh_page=False))
        tree.itemDoubleClicked.connect(select_home)
        def context(point):
            item=tree.itemAt(point)
            if not item:return
            tree.setCurrentItem(item);vid=chosen();menu=ActionMenu(tree)
            def favorite():self.instances.update(vid,favorite=not self.instances.get(vid).favorite);render()
            def tags():
                from PySide6.QtWidgets import QInputDialog
                value,ok=QInputDialog.getText(self,'实例标签','多个标签用逗号分隔',text=', '.join(self.instances.get(vid).tags))
                if ok:self.instances.update(vid,tags=value);self.build_versions()
            menu.addAction('取消收藏' if self.instances.get(vid).favorite else '收藏实例',favorite);menu.addAction('编辑标签',tags);menu.addSeparator()
            for title,callback in [('选择并返回首页',select_home),('重命名实例',lambda:self.rename_instance(vid)),('管理实例',lambda:self.instance_settings(vid)),('启动游戏',lambda:self.launch_version_id(vid)),('打开目录',lambda:self.open_folder(self.repo.run_dir(vid))),('导出整合包',lambda:self.export_modpack(vid)),('移入恢复中心',lambda:self.delete_version(vid))]:menu.addAction(title,callback)
            menu.exec(tree.viewport().mapToGlobal(point))
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);tree.customContextMenuRequested.connect(context)
        actions=row(spacing=4);manage_button=button('管理',manage,glyph='settings');actions.addWidget(manage_button)
        create_button=button('新建',self.create_instance,glyph='plus');actions.addWidget(create_button)
        actions.addWidget(button('导入',self.import_modpack,glyph='package'));actions.addWidget(button('恢复',self.recovery,glyph='history'));actions.addStretch()
        use_button=button('使用此实例',select_home,'primary');actions.addWidget(use_button);body.addLayout(actions)
        def selection_state():
            available=bool(chosen());manage_button.setEnabled(available);use_button.setEnabled(available)
            create_button.setEnabled(bool(self.selected_version))
        tree.currentItemChanged.connect(lambda *_:selection_state())
        query.textChanged.connect(render);kinds.currentIndexChanged.connect(render);sort.currentIndexChanged.connect(render);favorites.currentIndexChanged.connect(render);tags.currentIndexChanged.connect(render);render();selection_state()

    def build_about(self):
        body=self.page('about')
        card=Card('Onion Minecraft Launcher','免费、开源、公益的 Minecraft Java 版启动器。')
        card.body.addWidget(label('版本 '+self.config_obj.get('launcher_version'),'muted'))
        card.body.addSpacing(8)
        card.body.addWidget(label('Onion 启动器参考 HMCL、Axolotl（美西螈）等启动器的开源实现与交互设计进行重构，使用 Python 与 Qt 实现。感谢这些项目的开发者及开源社区的贡献。','',True))
        card.body.addWidget(label('本项目自有代码基于 MIT 协议开源。第三方组件遵循各自的开源协议。','muted',True))
        source=row();source.addWidget(button('查看源代码',lambda:QDesktopServices.openUrl(QUrl('https://github.com/Pomelene/Onion-MC-Launcher')),'soft','github'));source.addStretch()
        card.body.addLayout(source);body.addWidget(card)
        body.addStretch()
        footer=row();notice=label('Minecraft 为 Mojang / Microsoft 的商标，本项目与其无隶属关系。','muted',True)
        footer.addWidget(notice,1)
        footer.addWidget(button('反馈问题',lambda:QDesktopServices.openUrl(QUrl('https://github.com/Pomelene/Onion-MC-Launcher/issues')),'soft','feedback'))
        body.addLayout(footer)

    def launch_version_id(self,vid):
        if self.set_selected(vid):self.launch_selected()

    def build_download(self):
        from .browser import ContentBrowser
        kind=getattr(self,'download_kind','mod');page=self.page_map['download']
        if not hasattr(self,'download_browsers'):self.download_browsers={}
        while page.body.count():
            item=page.body.takeAt(0)
            if item.widget():item.widget().setParent(None)
        if kind=='tasks':
            from .task_center import TaskCenter
            if not hasattr(self,'download_tasks'):
                self.download_tasks=TaskCenter(self);self.download_tasks.layout().setContentsMargins(24,20,24,20)
            page.body.addWidget(self.download_tasks);self.download_tasks.show();self.download_tasks.refresh();return
        browser=self.download_browsers.get(kind)
        if browser is None or browser.repo is not self.repo:
            if browser is not None:browser.request_id+=1;browser.deleteLater()
            browser=ContentBrowser(self,kind);self.download_browsers[kind]=browser
        else:browser.sync_target()
        page.body.addWidget(browser,1);browser.show();self.download_browser=browser

    def open_content_download(self,kind):
        self.download_kind={'mods':'mod','resourcepacks':'resourcepack','shaderpacks':'shader'}[kind];self.navigate('download')

    def choose_project_version(self,project_id,title,kind,game,loader,vid):
        from .project_versions import ProjectVersions
        if self.current_page!='download' or getattr(self,'download_kind','mod')!=kind:self.choose_download_kind(kind)
        self.show_subpage(ProjectVersions(self,project_id,title,kind,game,loader,vid))

    def load_catalog_icon(self,item,url):
        from shiboken6 import isValid
        def work(job):
            from ..network import secure_open
            from .content_icons import MAX_ICON_BYTES
            if not url.startswith('https://'):return b''
            from urllib.request import Request
            with secure_open(Request(url,headers={'User-Agent':'OnionMinecraftLauncher'}),timeout=8) as response:data=response.read(MAX_ICON_BYTES+1)
            return data if len(data)<=MAX_ICON_BYTES else b''
        self.tasks.submit(work,lambda data:item.set_artwork(data) if isValid(item) else None,lambda error:None)

    def install_project(self,project_id,kind,game,loader,version_id=None,release_id=None):
        vid=self.selected_version if version_id is None else version_id
        if not vid and kind!='modpack':self.error('请先选择一个游戏实例。');return
        repo=self.repo;run=repo.run_dir(vid) if vid else repo.game_dir
        def work(job):
            from ..catalog import versions,pick_version,download_version
            if vid and kind!='modpack':repo.assert_idle(vid)
            target=repo.game_dir/'.cache/modpacks' if kind=='modpack' else run/{'mod':'mods','resourcepack':'resourcepacks','shader':'shaderpacks'}[kind];repo.assert_writable(target)
            available=versions(repo.downloader,project_id)
            if release_id is not None:available=[v for v in available if v.get('id')==release_id]
            chosen=pick_version(available,game,loader)
            if not chosen:raise RuntimeError('没有适配当前版本或加载器的文件。')
            if kind=='mod':
                from ..mod_plan import build_plan
                from ..mod_updates import install_selected
                plan=build_plan(repo.downloader,target,[chosen],game,loader,job)
                selected=[dict(path=target/e['old'] if e['old'] else None,latest=e['version'],old_sha1=plan['before'].get(e['old'],'')) for e in plan['entries'] if e['action']!='保留']
                install_selected(repo,vid,selected,job);return None
            target.mkdir(parents=True,exist_ok=True);job.emit('正在下载项目文件');path=download_version(repo.downloader,chosen,target)
            if kind=='modpack':
                from ..modpack import import_modpack
                return import_modpack(repo,path,job.emit,lambda a,b:job.emit((a,b)))
            return None
        def start():
            if self.repo is not repo:self.error('游戏目录已切换，请回到原目录重新安装');return
            return self.task('安装内容',work,lambda installed:self.installed(installed) if installed else self.status.setText('内容已安装'),retry=start,task_repo=repo,task_instance=vid)
        return start()

    def build_mods(self,content_kind='mods'):
        body=self.page('mods');seq=self.page_seq['mods'];vid=self.selected_version
        if not vid:body.addWidget(Empty('先选择一个游戏实例','所有内容都按实例独立管理。','grid','选择实例',lambda:self.navigate('versions')));return
        tabs=row();kind=ChoiceComboBox()
        for title,key in [('模组','mods'),('资源包','resourcepacks'),('光影','shaderpacks')]:kind.addItem(title,key)
        kind.setCurrentIndex(max(0,kind.findData(content_kind)));kind.hide()
        if content_kind=='mods':
            tabs.addWidget(button('检查并更新',lambda:self.update_mods(vid),glyph='refresh'))
        tabs.addWidget(button('打开目录',lambda:self.open_folder(self.repo.run_dir(vid)/content_kind),glyph='folder'));tabs.addWidget(button('搜索安装',lambda:self.open_content_download(content_kind),'soft','search'));body.addLayout(tabs)
        query=QLineEdit();query.setPlaceholderText('搜索名称、版本、说明或文件名');tabs.addWidget(query,1)
        holder=QWidget();results=column(holder,0,0);body.addWidget(holder)
        visible_rows=[]
        def filter_rows():
            text=query.text().strip().casefold()
            for widget,content in visible_rows:widget.setVisible(text in content)
        query.textChanged.connect(filter_rows)
        def refresh():
            key=kind.currentData();path=self.repo.run_dir(vid)/key;clear(results);results.addWidget(label('正在读取内容…','muted'))
            def scan(job):
                from ..mods import scan_mods,scan_resourcepacks,scan_shaderpacks
                from .content_icons import read_content_icon
                items={'mods':scan_mods,'resourcepacks':scan_resourcepacks,'shaderpacks':scan_shaderpacks}[key](path) if path.exists() else []
                items.sort(key=lambda i:(i.name.casefold(),i.path.name.casefold(),i.path.name))
                return [(info,read_content_icon(info.path)) for info in items]
            def done(items):
                if self.page_seq.get('mods')!=seq or kind.currentData()!=key:return
                clear(results);visible_rows.clear()
                if not items:results.addWidget(Empty('尚未添加内容','为当前实例下载适配的模组、资源包或光影。','package','搜索安装',lambda:self.open_content_download(content_kind)));return
                for info,artwork in items:
                    version=getattr(info,'version','');title=info.name+('  ·  '+version if version else '')
                    detail=' · '.join(str(value) for value in (getattr(info,'mod_id',''),getattr(info,'description',''),info.path.name,info.size_text) if value)
                    state=[info]
                    item=ContentRow(title,detail,{'mods':'package','resourcepacks':'grid','shaderpacks':'world'}[key],info.enabled if key=='mods' else None)
                    if item.check:item.check.clicked.connect(lambda checked=False,s=state,r=item:self.toggle_mod(s,vid,r))
                    item.set_artwork(artwork)
                    item.action('打开所在目录',lambda s=state:self.open_folder(s[0].path.parent),'folder')
                    item.action('移入恢复中心',lambda s=state:self.remove_content(s[0].path,vid,refresh),'trash','danger')
                    results.addWidget(item);visible_rows.append((item,(title+' '+detail).casefold()))
                filter_rows()
            self.tasks.submit(scan,done,self.error)
        tabs.insertWidget(0,button('刷新',refresh,glyph='history'));kind.currentIndexChanged.connect(refresh);refresh()

    def toggle_mod(self,state,vid,item):
        from ..mods import set_mod_enabled
        from shiboken6 import isValid
        info=state[0]
        def restore():
            if isValid(item):item.check.setChecked(state[0].enabled);item.check.setEnabled(True)
        if self.mutating:
            restore();self.status.setText('已有文件操作进行中，请稍候');return
        self.mutating=True;item.check.setEnabled(False)
        def work(job):self.repo.assert_idle(vid);self.repo.assert_writable(info.path);return set_mod_enabled(info,not info.enabled)
        def done(updated):
            self.mutating=False;state[0]=updated
            if isValid(item):
                item.text.detail=item.text.detail.replace(info.path.name,updated.path.name);item.text.setToolTip(item.text.title+'\n'+item.text.detail);item.text.update();restore()
            self.status.setText(('已启用 · ' if updated.enabled else '已禁用 · ')+updated.name)
        def failed(error):
            self.mutating=False;restore();self.status.setText('模组状态更新失败：'+str(error))
        self.tasks.submit(work,done,failed)

    def remove_content(self,path,vid,refresh):
        if QMessageBox.question(self,'移除内容','将 '+path.name+' 移入恢复中心？')!=QMessageBox.StandardButton.Yes:return
        from ..safety import recycle
        def work(job):self.repo.assert_idle(vid);self.repo.assert_writable(path);return recycle(path,path.parent)
        self.task('移除内容',work,lambda _:refresh())

    def build_worlds(self):
        body=self.page('worlds');seq=self.page_seq['worlds'];vid=self.selected_version
        if not vid:body.addWidget(Empty('先选择一个游戏实例','选择实例后查看它的世界存档。','world','选择实例',lambda:self.navigate('versions')));return
        actions=row();actions.addWidget(label(str(self.repo.saves_dir(vid)),'muted'),1);actions.addWidget(button('恢复备份',self.restore_world,'soft'));body.addLayout(actions)
        holder=QWidget();results=column(holder);body.addWidget(holder);results.addWidget(label('正在读取世界存档…','muted'))
        from ..worlds import list_worlds
        def done(worlds):
            if self.page_seq.get('worlds')!=seq:return
            clear(results)
            if not worlds:results.addWidget(Empty('世界等待你来创造','创建世界后会显示在这里，也可以从 ZIP 备份恢复。','world','恢复备份',self.restore_world));return
            for world in worlds:
                card=Card(world.name,f'{world.version}  ·  {world.game_mode}  ·  {world.last_played_text()}');line=row();line.addStretch()
                line.addWidget(button('打开目录',lambda w=world:self.open_folder(w.dir),glyph='folder'));line.addWidget(button('备份',lambda w=world:self.backup_world(w,vid),'soft'))
                line.addWidget(button('移除',lambda w=world:self.remove_content(w.dir,vid,lambda:self.navigate('worlds',force=True)),'danger'));card.body.addLayout(line);results.addWidget(card)
        self.tasks.submit(lambda job:list_worlds(self.repo.saves_dir(vid)),done,self.error)

    def backup_world(self,world,vid):
        from ..worlds import backup_world
        def work(job):self.repo.assert_idle(vid);return backup_world(world,self.repo.game_dir/'backups/worlds')
        self.task('备份世界',work,lambda path:self.status.setText('已备份 · '+str(path)))

    def restore_world(self):
        vid=self.selected_version
        if not vid:return
        path,_=QFileDialog.getOpenFileName(self,'恢复世界备份','','ZIP 备份 (*.zip)')
        if not path:return
        from ..saves import restore
        def work(job):self.repo.assert_idle(vid);return restore(Path(path),self.repo.saves_dir(vid),cancel_event=job.cancel)
        self.task('恢复世界备份',work,lambda _:self.navigate('worlds',force=True))

    def build_logs(self):
        body=self.page('logs');bar=row();bar.addWidget(button('打开实例日志',lambda:self.open_folder(self.repo.logs_dir(self.selected_version)) if self.selected_version else None,glyph='folder'))
        bar.addWidget(button('崩溃诊断',self.diagnose));bar.addWidget(button('环境体检',lambda:self.preflight(self.selected_version)));bar.addStretch();bar.addWidget(button('停止游戏',lambda:self.process.stop() if self.process and self.process.proc.poll() is None else None,'danger'));body.addLayout(bar)
        body.addWidget(self.logs,1)
        self.logs.setMinimumHeight(450)

    def diagnose(self):
        if not self.selected_version:return
        from .health_report import HealthReport
        self.show_subpage(HealthReport(self,self.selected_version,crash=True))

    def build_settings(self):
        from .settings import SettingsEditor
        body=self.page('settings');self.settings_editor=SettingsEditor(self,external_nav=True)
        self.settings_editor.setMinimumHeight(570);body.addWidget(self.settings_editor,1)

    def manage_java(self,on_selected=None):
        self.navigate('settings')
        self.settings_editor.java_manager.on_selected=on_selected
        self.open_settings_tab(self.settings_editor.tab_names['Java 管理'])
