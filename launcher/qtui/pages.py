"""Qt pages delegate filesystem, network and installation work to existing services."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QLineEdit,QComboBox,QFormLayout,QCheckBox,QSpinBox,
    QTabWidget,QFileDialog,QMessageBox,QDialog,QTreeWidget,QTreeWidgetItem,QMenu)
from .widgets import Page,Card,Empty,HomeCanvas,ContentRow,label,button,column,row,clear,icon


class Pages:
    def build_home(self):
        body=self.page('home');canvas=HomeCanvas(self.config_obj.get('background_image') or '')
        overlay=column(canvas,30,12);overlay.addStretch()
        bottom=row(spacing=20);caption=column(spacing=4)
        caption.addWidget(label('MINECRAFT JAVA EDITION','eyebrow'))
        self.wallpaper_button=button('自定义首页背景',self.open_appearance)
        self.wallpaper_button.setStyleSheet('color:white;background:rgba(255,255,255,28);text-align:left;')
        caption.addWidget(self.wallpaper_button);bottom.addLayout(caption);bottom.addStretch()
        start=QWidget();start.setObjectName('startPanel');actions=row(start,0,0)
        self.launch_button=button('',self.launch_selected,'primary','play');self.launch_button.setMinimumSize(238,78)
        self.launch_button.setStyleSheet('QPushButton {border-top-right-radius:0;border-bottom-right-radius:0;font-size:16px;text-align:left;padding:12px 24px;}')
        self.quick_button=button('',self.quick_select,'primary','up');self.quick_button.setToolTip('快捷选择实例');self.quick_button.setFixedSize(48,78)
        self.quick_button.setStyleSheet('QPushButton {border-top-left-radius:0;border-bottom-left-radius:0;border-left:1px solid rgba(255,255,255,60);font-size:22px;}')
        actions.addWidget(self.launch_button);actions.addWidget(self.quick_button);bottom.addWidget(start)
        overlay.addLayout(bottom);body.addWidget(canvas,1);self.update_selection()

    def open_appearance(self):
        self.navigate('settings');self.settings_editor.select_tab(self.settings_editor.tab_names['外观'])

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
        body=self.page('versions');toolbar=row();query=QLineEdit();self.library_search=query;query.setPlaceholderText('搜索实例名称、版本或分组');query.setText(getattr(self,'library_query',''));toolbar.addWidget(query,1)
        kinds=QComboBox();kinds.addItems(['全部类型','原版','Fabric','Forge','NeoForge','Quilt','OptiFine']);kinds.setCurrentIndex(getattr(self,'library_kind',0));toolbar.addWidget(kinds)
        sort=QComboBox();sort.addItems(['名称排序','最近游玩','游玩时长']);sort.setCurrentIndex(getattr(self,'library_sort',0));toolbar.addWidget(sort)
        toolbar.addWidget(button('安装游戏',self.install_dialog,'primary','plus'));toolbar.addWidget(button('导入整合包',self.import_modpack,glyph='package'));body.addLayout(toolbar)
        library=row();library.addWidget(label(str(self.repo.game_dir),'muted',True),1);library.addWidget(button('切换游戏目录',lambda:self.navigate('settings'),glyph='folder'));library.addWidget(button('刷新',self.reload_versions));body.addLayout(library)
        tree=QTreeWidget();self.version_tree=tree;tree.setRootIsDecorated(False);tree.setHeaderLabels(['实例名称','游戏版本 / 加载器','分组','上次游玩']);tree.setColumnWidth(0,240);tree.setColumnWidth(1,240);tree.setColumnWidth(2,100);tree.setMinimumHeight(380);body.addWidget(tree,1)
        summary=label('','muted');body.addWidget(summary)
        def render():
            self.library_query=query.text();self.library_kind=kinds.currentIndex();self.library_sort=sort.currentIndex();tree.clear();text=query.text().strip().lower()
            versions=[v for v in self.versions if (kinds.currentIndex()==0 or self.kinds.get(v)==kinds.currentText()) and text in (v+' '+self.instances.display_name(v)+' '+self.instances.get(v).group).lower()]
            versions.sort(key=(lambda v:self.instances.display_name(v).lower()) if sort.currentIndex()==0 else (lambda v:self.instances.get(v).last_played) if sort.currentIndex()==1 else (lambda v:self.instances.get(v).play_seconds),reverse=sort.currentIndex()!=0)
            for vid in versions:
                meta=self.instances.get(vid);item=QTreeWidgetItem([meta.display_name,vid+' · '+self.kinds.get(vid,'原版'),meta.group,meta.last_played_text()]);item.setData(0,Qt.ItemDataRole.UserRole,vid);tree.addTopLevelItem(item)
                if vid==self.selected_version:tree.setCurrentItem(item)
            summary.setText(f'{len(versions)} / {len(self.versions)} 个实例 · 单击选择，双击返回首页 · 右键管理实例')
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
            tree.setCurrentItem(item);vid=chosen();menu=QMenu(tree)
            for title,callback in [('选择并返回首页',select_home),('重命名实例',lambda:self.rename_instance(vid)),('管理实例',lambda:self.instance_settings(vid)),('启动游戏',lambda:self.launch_version_id(vid)),('打开目录',lambda:self.open_folder(self.repo.run_dir(vid))),('导出整合包',lambda:self.export_modpack(vid)),('移入恢复中心',lambda:self.delete_version(vid))]:menu.addAction(title,callback)
            menu.exec(tree.viewport().mapToGlobal(point))
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);tree.customContextMenuRequested.connect(context)
        query.textChanged.connect(render);kinds.currentIndexChanged.connect(render);sort.currentIndexChanged.connect(render);render()
        actions=row();actions.addWidget(button('管理选中实例',manage,'soft','settings'));actions.addWidget(button('重命名实例',lambda:self.rename_instance(chosen()) if chosen() else None));actions.addWidget(button('新建独立实例',self.create_instance,glyph='plus'));actions.addWidget(button('恢复中心',self.recovery,glyph='history'));actions.addStretch();actions.addWidget(button('使用此实例',select_home,'primary'));body.addLayout(actions)

    def build_about(self):
        body=self.page('about');card=Card('Onion Minecraft Launcher','免费、开源、公益的 Minecraft Java 版启动器。')
        card.body.addWidget(label('版本 '+self.config_obj.get('launcher_version')+'  ·  MIT License','muted'))
        card.body.addWidget(label('界面操作结构参考 HMCL 与美西螈，使用 Python 与 Qt 实现。Minecraft 为 Mojang / Microsoft 的商标，本项目与其无隶属关系。','muted',True))
        card.body.addWidget(button('查看项目源代码',lambda:QDesktopServices.openUrl(QUrl('https://github.com/Pomelene/Onion-MC-Launcher')),'soft'))
        body.addWidget(card)

    def launch_version_id(self,vid):
        if self.set_selected(vid):self.launch_selected()

    def build_download(self):
        from .browser import ContentBrowser
        kind=getattr(self,'download_kind','mod');page=self.page_map['download']
        if not hasattr(self,'download_browsers'):self.download_browsers={}
        while page.body.count():
            item=page.body.takeAt(0)
            if item.widget():item.widget().setParent(None)
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
            from ..mods import install_dependencies
            if vid and kind!='modpack':repo.assert_idle(vid)
            target=repo.game_dir/'.cache/modpacks' if kind=='modpack' else run/{'mod':'mods','resourcepack':'resourcepacks','shader':'shaderpacks'}[kind];repo.assert_writable(target)
            available=versions(repo.downloader,project_id)
            if release_id is not None:available=[v for v in available if v.get('id')==release_id]
            chosen=pick_version(available,game,loader)
            if not chosen:raise RuntimeError('没有适配当前版本或加载器的文件。')
            target.mkdir(parents=True,exist_ok=True);job.emit('正在下载项目文件');path=download_version(repo.downloader,chosen,target)
            if kind=='modpack':
                from ..modpack import import_modpack
                return import_modpack(repo,path,job.emit,lambda a,b:job.emit((a,b)))
            if kind=='mod':install_dependencies(repo.downloader,chosen.get('id'),target,game,loader)
            return None
        return self.task('安装内容',work,lambda vid:self.installed(vid) if vid else self.status.setText('内容已安装'))

    def build_mods(self,content_kind='mods'):
        body=self.page('mods');seq=self.page_seq['mods'];vid=self.selected_version
        if not vid:body.addWidget(Empty('先选择一个游戏实例','所有内容都按实例独立管理。','grid','选择实例',lambda:self.navigate('versions')));return
        tabs=row();kind=QComboBox()
        for title,key in [('模组','mods'),('资源包','resourcepacks'),('光影','shaderpacks')]:kind.addItem(title,key)
        kind.setCurrentIndex(max(0,kind.findData(content_kind)));kind.hide()
        tabs.addWidget(label({'mods':'模组','resourcepacks':'资源包','shaderpacks':'光影'}[content_kind]+' · '+self.instances.display_name(vid),'muted'),1);tabs.addWidget(button('打开目录',lambda:self.open_folder(self.repo.run_dir(vid)/content_kind),glyph='folder'));tabs.addStretch();tabs.addWidget(button('搜索安装',lambda:self.open_content_download(content_kind),'soft','search'));body.addLayout(tabs)
        query=QLineEdit();query.setPlaceholderText('搜索名称、版本、说明或文件名');tabs.addWidget(query)
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
                line.addWidget(button('移除',lambda w=world:self.remove_content(w.dir,vid,lambda:self.navigate('worlds')),'danger'));card.body.addLayout(line);results.addWidget(card)
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
        self.task('恢复世界备份',work,lambda _:self.navigate('worlds'))

    def build_logs(self):
        body=self.page('logs');bar=row();bar.addWidget(button('打开实例日志',lambda:self.open_folder(self.repo.logs_dir(self.selected_version)) if self.selected_version else None,glyph='folder'))
        bar.addWidget(button('崩溃诊断',self.diagnose));bar.addStretch();bar.addWidget(button('停止游戏',lambda:self.process.stop() if self.process and self.process.proc.poll() is None else None,'danger'));body.addLayout(bar)
        body.addWidget(self.logs,1)
        self.logs.setMinimumHeight(450)

    def diagnose(self):
        if not self.selected_version:return
        from ..crash import latest_crash_report,summarize
        def work(job):
            report=latest_crash_report(self.repo.run_dir(self.selected_version))
            return summarize(report) if report else '没有发现崩溃报告。'
        self.tasks.submit(work,lambda text:QMessageBox.information(self,'崩溃诊断',text),self.error)

    def build_settings(self):
        from .settings import SettingsEditor
        body=self.page('settings');self.settings_editor=SettingsEditor(self,external_nav=True)
        self.settings_editor.setMinimumHeight(570);body.addWidget(self.settings_editor,1)

    def manage_java(self,on_selected=None):
        dialog=QDialog(self);dialog.setWindowTitle('Java 运行时');dialog.resize(760,460);body=column(dialog,24);body.addWidget(label('Java 运行时','title'))
        tree=QTreeWidget();tree.setHeaderLabels(['Java','路径']);tree.setColumnWidth(0,120);body.addWidget(tree,1);status=label('正在检测可用 Java…','muted',True);body.addWidget(status)
        def done(infos):
            tree.clear()
            for info in infos:
                item=QTreeWidgetItem([f'Java {info.major}',str(info.path)]);item.setData(0,Qt.ItemDataRole.UserRole,str(info.path));tree.addTopLevelItem(item)
            status.setText(f'发现 {len(infos)} 个运行时；游戏启动时也会按需自动下载匹配版本。')
        from ..java import find_all_java,download_java
        self.tasks.submit(lambda job:find_all_java(),done,lambda e:status.setText(str(e)))
        actions=row();major=QComboBox();major.addItems(['8','17','21','25']);actions.addWidget(major)
        def selected(path):
            if on_selected:on_selected(path)
            else:self.config_obj.set('java_path',str(path))
            dialog.accept();self.status.setText('Java 运行时已选择' if on_selected else 'Java 运行时已保存')
        def download():
            def installed(info):
                if info:selected(info.path)
                else:self.error('没有可用的官方 Java 运行时')
            self.task('下载 Java',lambda job:download_java(int(major.currentText()),self.repo.downloader,job.emit,lambda a,b:job.emit((a,b))),installed)
        actions.addWidget(button('下载官方运行时',download,'soft','download'));actions.addStretch()
        def choose():
            if tree.currentItem():selected(tree.currentItem().data(0,Qt.ItemDataRole.UserRole))
        actions.addWidget(button('使用所选',choose,'primary'));body.addLayout(actions);self.dialogs.append(dialog);dialog.open()
