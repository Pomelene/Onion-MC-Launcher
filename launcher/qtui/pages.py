"""Qt pages delegate filesystem, network and installation work to existing services."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QLineEdit,QComboBox,QFormLayout,QCheckBox,QSpinBox,
    QTabWidget,QFileDialog,QMessageBox,QDialog,QTreeWidget,QTreeWidgetItem,QMenu)
from .widgets import Page,Card,Empty,label,button,column,row,clear,icon


class Pages:
    def build_home(self):
        body=self.page('home');vid=self.selected_version
        hero=Card();hero.setObjectName('hero');hero.body.setContentsMargins(30,28,30,28)
        hero.body.addWidget(label('MINECRAFT JAVA EDITION','eyebrow'))
        title=label(self.instances.display_name(vid) if vid else '你的下一个世界，从这里开始','title',True);hero.body.addWidget(title)
        meta=self.instances.get(vid) if vid else None
        hero.body.addWidget(label((self.kinds.get(vid,'原版')+'  /  '+('上次游玩 '+meta.last_played_text() if meta and meta.last_played else '已准备就绪，开始第一次冒险')) if vid else '安装原版、选择加载器，或导入喜欢的整合包。','muted',True))
        actions=row();actions.addWidget(button('启动游戏' if vid else '安装游戏',self.launch_selected,'primary','play' if vid else 'download'))
        if vid:actions.addWidget(button('实例设置',lambda:self.instance_settings(vid),glyph='settings'))
        actions.addStretch();hero.body.addLayout(actions);body.addWidget(hero)
        tools=Card('游戏工作台');items=row()
        for title,desc,glyph,callback in [('安装游戏','原版与加载器','download',self.install_dialog),('导入整合包','Modrinth / CurseForge','package',self.import_modpack),('新建实例','独立模组与配置','plus',self.create_instance)]:
            group=column(spacing=5);group.addWidget(button(title,callback,'soft',glyph));group.addWidget(label(desc,'muted'));items.addLayout(group,1)
        tools.body.addLayout(items);body.addWidget(tools)
        account=self.accounts.current()
        if not account:
            card=Card('准备你的游戏身份','使用 Microsoft 正版账号登录，或为本地游戏添加离线身份。')
            card.body.addWidget(button('添加游戏账号',self.open_accounts,'soft','account'),alignment=Qt.AlignmentFlag.AlignLeft);body.addWidget(card)
        recent=[m for m in self.instances.all() if m.last_played and m.version_id in self.versions]
        if recent:
            card=Card('继续游玩')
            for meta in sorted(recent,key=lambda m:m.last_played,reverse=True)[:3]:
                line=row();texts=column(spacing=4);texts.addWidget(label(meta.display_name,'heading',True));texts.addWidget(label(meta.last_played_text(),'muted'));line.addLayout(texts,1)
                line.addWidget(button('选择',lambda v=meta.version_id:self.set_selected(v),glyph='arrow'));card.body.addLayout(line)
            body.addWidget(card)
        else:body.addWidget(Empty('每段冒险，都有一个起点','开始游玩后，最近的世界会自动整理在这里。','history'))
        footer=row();footer.addWidget(label(f'游戏库  {self.repo.game_dir}','muted',True),1);footer.addWidget(button(f'{len(self.versions)} 个实例',lambda:self.navigate('versions')));body.addLayout(footer)

    def build_versions(self):
        body=self.page('versions');bar=row();query=QLineEdit();query.setPlaceholderText('搜索实例名称或分组');bar.addWidget(query,1)
        kinds=QComboBox();kinds.addItems(['全部类型','原版','Fabric','Forge','NeoForge','Quilt','OptiFine']);bar.addWidget(kinds)
        bar.addWidget(button('新建实例',self.create_instance,glyph='plus'));bar.addWidget(button('安装游戏',self.install_dialog,'primary','download'));body.addLayout(bar)
        content=QWidget();results=column(content);body.addWidget(content)
        def render():
            clear(results);text=query.text().strip().lower()
            versions=[v for v in self.versions if (kinds.currentIndex()==0 or self.kinds.get(v)==kinds.currentText()) and text in (v+' '+self.instances.display_name(v)+' '+self.instances.get(v).group).lower()]
            if not versions:results.addWidget(Empty('添加你的游戏实例' if not self.versions else '没有找到匹配的实例','安装新版本，或换个关键词试试。','grid','安装游戏',self.install_dialog));return
            for vid in versions:
                card=Card();card.body.setContentsMargins(18,15,18,15);line=row();texts=column(spacing=5)
                texts.addWidget(label(self.instances.display_name(vid),'heading',True));texts.addWidget(label(vid+'  ·  '+self.kinds.get(vid,'原版'),'muted',True));line.addLayout(texts,1)
                line.addWidget(button('启动',lambda v=vid:self.launch_version_id(v),'primary','play'))
                line.addWidget(button('设置',lambda v=vid:self.instance_settings(v),glyph='settings'))
                more=button('更多');menu=QMenu(more)
                for title,callback in [('选择此实例',lambda v=vid:self.set_selected(v)),('打开目录',lambda v=vid:self.open_folder(self.repo.run_dir(v))),('校验文件',lambda v=vid:self.verify_version(v)),('导出整合包',lambda v=vid:self.export_modpack(v)),('移入恢复中心',lambda v=vid:self.delete_version(v))]:
                    menu.addAction(title,callback)
                more.setMenu(menu);line.addWidget(more);card.body.addLayout(line);results.addWidget(card)
        query.textChanged.connect(render);kinds.currentIndexChanged.connect(render);render()
        body.addWidget(button('恢复中心',self.recovery,glyph='history'),alignment=Qt.AlignmentFlag.AlignLeft)

    def launch_version_id(self,vid):
        self.set_selected(vid);self.launch_selected()

    def build_download(self):
        body=self.page('download');seq=self.page_seq['download'];actions=row();actions.addWidget(button('安装游戏 / 加载器',self.install_dialog,'primary','download'));actions.addWidget(button('导入整合包',self.import_modpack,glyph='package'));actions.addStretch();body.addLayout(actions)
        search=Card();bar=row();kinds=QComboBox()
        for text,value in [('模组','mod'),('资源包','resourcepack'),('光影','shader'),('整合包','modpack')]:kinds.addItem(text,value)
        query=QLineEdit();query.setPlaceholderText('搜索名称、作者或关键词');bar.addWidget(kinds);bar.addWidget(query,1)
        go=button('搜索',role='primary',glyph='search');bar.addWidget(go);search.body.addLayout(bar)
        filters=row();game=QLineEdit();game.setPlaceholderText('不限游戏版本');game.setMaximumWidth(180);loader=QComboBox()
        for text,value in [('不限加载器',''),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt')]:loader.addItem(text,value)
        if self.selected_version:
            from ..modpack import _base_version,_detect_loader
            game.setText(_base_version(self.repo,self.selected_version));loader.setCurrentIndex(max(0,loader.findData(_detect_loader(self.repo,self.selected_version)[0])))
        filters.addWidget(label('游戏版本','muted'));filters.addWidget(game);filters.addSpacing(15);filters.addWidget(label('加载器','muted'));filters.addWidget(loader);filters.addStretch();search.body.addLayout(filters);body.addWidget(search)
        results_widget=QWidget();results=column(results_widget);body.addWidget(results_widget)
        results.addWidget(Empty('发现你的下一份灵感','搜索模组、资源包、光影或整合包，并安装到当前实例。','search'))
        def run_search():
            text=query.text().strip()
            if not text:query.setFocus();return
            from ..catalog import search as find
            kind,version,load=kinds.currentData(),game.text().strip(),loader.currentData()
            go.setEnabled(False)
            def done(data):
                if self.page_seq.get('download')!=seq:return
                go.setEnabled(True);clear(results);hits=data.get('hits') or []
                if not hits:results.addWidget(Empty('没有找到匹配的内容','试试更短的关键词，或放宽版本条件。','search'));return
                for hit in hits[:20]:
                    card=Card(hit.get('title') or hit.get('slug') or '项目',hit.get('description') or '')
                    line=row();line.addWidget(label(f"{hit.get('author') or ''}  ·  下载 {hit.get('downloads') or 0}",'muted'),1)
                    line.addWidget(button('安装',lambda pid=hit['project_id'],k=kind,g=version,l=load:self.install_project(pid,k,g,l),'soft','download'));card.body.addLayout(line);results.addWidget(card)
            def failed(error):
                if self.page_seq.get('download')==seq:go.setEnabled(True);self.error(error)
            self.tasks.submit(lambda job:find(self.repo.downloader,kind,text,version,load,limit=30),done,failed)
        go.clicked.connect(run_search);query.returnPressed.connect(run_search)

    def install_project(self,project_id,kind,game,loader):
        vid=self.selected_version
        if not vid:self.error('请先选择一个游戏实例。');return
        repo=self.repo;run=repo.run_dir(vid)
        def work(job):
            from ..catalog import versions,pick_version,download_version
            from ..mods import install_dependencies
            repo.assert_idle(vid);target=run/{'mod':'mods','resourcepack':'resourcepacks','shader':'shaderpacks','modpack':'modpacks'}[kind];repo.assert_writable(target)
            chosen=pick_version(versions(repo.downloader,project_id),game,loader)
            if not chosen:raise RuntimeError('没有适配当前版本或加载器的文件。')
            target.mkdir(parents=True,exist_ok=True);job.emit('正在下载项目文件');path=download_version(repo.downloader,chosen,target)
            if kind=='modpack':
                from ..modpack import import_modpack
                return import_modpack(repo,path,job.emit,lambda a,b:job.emit((a,b)))
            if kind=='mod':install_dependencies(repo.downloader,chosen.get('id'),target,game,loader)
            return None
        self.task('安装内容',work,lambda vid:self.installed(vid) if vid else self.status.setText('内容已安装'))

    def build_mods(self):
        body=self.page('mods');seq=self.page_seq['mods'];vid=self.selected_version
        if not vid:body.addWidget(Empty('先选择一个游戏实例','所有内容都按实例独立管理。','grid','选择实例',lambda:self.navigate('versions')));return
        tabs=row();kind=QComboBox()
        for title,key in [('模组','mods'),('资源包','resourcepacks'),('光影','shaderpacks')]:kind.addItem(title,key)
        tabs.addWidget(kind);tabs.addStretch();tabs.addWidget(button('搜索安装',lambda:self.navigate('download'),'soft','search'));body.addLayout(tabs)
        holder=QWidget();results=column(holder);body.addWidget(holder)
        def refresh():
            key=kind.currentData();path=self.repo.run_dir(vid)/key;clear(results);results.addWidget(label('正在读取内容…','muted'))
            def scan(job):
                from ..mods import scan_mods,scan_resourcepacks,scan_shaderpacks
                return {'mods':scan_mods,'resourcepacks':scan_resourcepacks,'shaderpacks':scan_shaderpacks}[key](path) if path.exists() else []
            def done(items):
                if self.page_seq.get('mods')!=seq or kind.currentData()!=key:return
                clear(results)
                if not items:results.addWidget(Empty('为你的世界添加更多可能','这个实例还没有添加此类内容。','package','浏览下载中心',lambda:self.navigate('download')));return
                for info in items:
                    card=Card(info.name);line=row();line.addWidget(label(info.path.name,'muted',True),1)
                    if key=='mods':line.addWidget(button('禁用' if info.enabled else '启用',lambda i=info:self.toggle_mod(i,vid,refresh),'soft'))
                    line.addWidget(button('移除',lambda i=info:self.remove_content(i.path,vid,refresh),'danger'));card.body.addLayout(line);results.addWidget(card)
            self.tasks.submit(scan,done,self.error)
        kind.currentIndexChanged.connect(refresh);refresh()

    def toggle_mod(self,info,vid,refresh):
        from ..mods import set_mod_enabled
        def work(job):self.repo.assert_idle(vid);self.repo.assert_writable(info.path);return set_mod_enabled(info,not info.enabled)
        self.task('更新模组状态',work,lambda _:refresh())

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
        self.logs.setParent(self.page_map['logs'].content);body.addWidget(self.logs,1)
        self.logs.setMinimumHeight(450)

    def diagnose(self):
        if not self.selected_version:return
        from ..crash import latest_crash_report,summarize
        def work(job):
            report=latest_crash_report(self.repo.run_dir(self.selected_version))
            return summarize(report) if report else '没有发现崩溃报告。'
        self.tasks.submit(work,lambda text:QMessageBox.information(self,'崩溃诊断',text),self.error)

    def build_settings(self):
        body=self.page('settings');card=Card('游戏与运行环境','修改后保存，仅影响后续启动。');form=QFormLayout();form.setSpacing(14);fields={}
        for key,title,hint in [('game_dir','游戏目录',r'F:\.minecraft'),('java_path','Java 可执行文件','自动选择匹配的 Java'),('jvm_args','JVM 参数','可选，空格分隔'),('game_args','游戏参数','可选，空格分隔'),('server_address','自动加入服务器','可选，host:port'),('proxy_host','下载代理主机','可选，留空使用直连'),('microsoft_client_id','Microsoft 应用 client_id','正版登录应用，可在账号窗口中配置')]:
            edit=QLineEdit(str(self.config_obj.get(key) or ''));edit.setPlaceholderText(hint);fields[key]=edit;form.addRow(title,edit)
        for key,title,low,high in [('min_memory','最小内存 MB',512,65536),('max_memory','最大内存 MB',512,65536),('window_width','游戏窗口宽度',320,7680),('window_height','游戏窗口高度',240,4320),('max_download_threads','并发下载数',1,32),('download_speed_limit','总限速 KB/s（0 不限）',0,100000),('proxy_port','下载代理端口',0,65535)]:
            spin=QSpinBox();spin.setRange(low,high);spin.setValue(int(self.config_obj.get(key) or low if key not in ('proxy_port','download_speed_limit') else self.config_obj.get(key) or 0));fields[key]=spin;form.addRow(title,spin)
        source=QComboBox()
        for title,key in [('Mojang 官方','mojang'),('BMCLAPI 镜像','bmclapi'),('MCBBS 镜像','mcbbbs')]:source.addItem(title,key)
        source.setCurrentIndex(max(0,source.findData(self.config_obj.get('download_source'))));fields['download_source']=source;form.addRow('下载源',source)
        for key,title in [('version_isolation','默认隔离每个游戏实例'),('fullscreen','全屏启动游戏'),('demo','试玩模式'),('close_after_launch','游戏启动后收起启动器'),('keep_launcher_open','游戏退出后保留启动器')]:
            box=QCheckBox(title);box.setChecked(bool(self.config_obj.get(key)));fields[key]=box;form.addRow('',box)
        card.body.addLayout(form)
        def save():
            if self.mutating:self.error('请先结束当前文件操作，再修改全局设置');return
            data={}
            for key,field in fields.items():
                data[key]=field.isChecked() if isinstance(field,QCheckBox) else field.value() if isinstance(field,QSpinBox) else field.currentData() if isinstance(field,QComboBox) else field.text().strip()
            if data['min_memory']>data['max_memory']:self.error('最小内存不能大于最大内存');return
            for key,value in data.items():self.config_obj.set(key,value)
            from ..repository import GameRepository
            self.repo=GameRepository(self.config_obj);self.reload_versions();self.status.setText('设置已保存')
        actions=row();actions.addWidget(button('管理 Java',self.manage_java,glyph='java'));actions.addStretch();actions.addWidget(button('保存设置',save,'primary'));card.body.addLayout(actions);body.addWidget(card)
        about=Card('Onion Minecraft Launcher','参考 HMCL 的账号、下载与实例管理流程。游戏数据继续使用 F 盘游戏库。')
        about.body.addWidget(button('恢复中心',self.recovery,glyph='history'),alignment=Qt.AlignmentFlag.AlignLeft);body.addWidget(about)

    def manage_java(self):
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
        def download():
            def installed(info):
                if info:self.config_obj.set('java_path',str(info.path));dialog.accept();self.status.setText('Java 运行时已安装')
                else:self.error('没有可用的官方 Java 运行时')
            self.task('下载 Java',lambda job:download_java(int(major.currentText()),self.repo.downloader,job.emit,lambda a,b:job.emit((a,b))),installed)
        actions.addWidget(button('下载官方运行时',download,'soft','download'));actions.addStretch()
        def choose():
            if tree.currentItem():self.config_obj.set('java_path',tree.currentItem().data(0,Qt.ItemDataRole.UserRole));dialog.accept();self.navigate('settings')
        actions.addWidget(button('使用所选',choose,'primary'));body.addLayout(actions);self.dialogs.append(dialog);dialog.open()
