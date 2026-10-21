"""Qt actions adapt existing launcher services without a second implementation."""
import json
import shlex
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QComboBox,QInputDialog,
    QFileDialog,QMessageBox,QTreeWidget,QTreeWidgetItem)
from .widgets import column,row,label,button,Card
from ..paths import LAUNCHER_VERSION,LAUNCHER_NAME


class Actions:
    def launch_selected(self):
        vid=self.selected_version
        if not vid:self.install_dialog();return
        if self.launch_pending or self.process and self.process.proc.poll() is None:self.error('游戏已在运行或启动准备中。');return
        record=self.accounts.current()
        if not record:self.open_accounts();return
        self.launch_pending=True;self.running_version=vid
        repo=self.repo;overrides=self.version_settings.resolve(vid,self.config_obj)
        def work(job):
            from ..launch import Account,LaunchSettings,launch
            from ..java import resolve_java
            job.emit('正在验证账号')
            fresh=self.accounts.refresh(record) if record.is_expired() else record
            rv=repo.install(vid,job.emit,lambda a,b:job.emit((a,b)))
            java=resolve_java(rv.java_major,overrides['java_path'],repo.downloader,job.emit,lambda a,b:job.emit((a,b)))
            if not java:raise RuntimeError('未找到可用 Java，请在设置中安装运行时。')
            if job.cancel.is_set():raise RuntimeError('启动已取消')
            injector=''
            if fresh.authlib_url:
                from ..auth.authlib import ensure_injector
                injector=str(ensure_injector(repo.downloader,repo.game_dir/'.cache/authlib-injector.jar'))
            settings=LaunchSettings(java_path=str(java.path),min_memory=overrides['min_memory'],max_memory=overrides['max_memory'],
                width=overrides['width'],height=overrides['height'],fullscreen=overrides['fullscreen'],demo=bool(self.config_obj.get('demo')),
                server_address=overrides['server_address'],extra_jvm_args=shlex.split(overrides['jvm_args']),extra_game_args=shlex.split(overrides['game_args']),
                launcher_name=LAUNCHER_NAME,launcher_version=LAUNCHER_VERSION,authlib_injector_jar=injector)
            account=Account(fresh.username,fresh.uuid,fresh.access_token or '0',fresh.user_type,fresh.authlib_url,fresh.client_id,fresh.xuid)
            def logged(text,is_error):
                if fresh.access_token and fresh.access_token!='0':text=text.replace(fresh.access_token,'[已隐藏令牌]')
                self.game_log.emit(text,is_error)
            process=launch(repo,rv,account,settings,str(java.path),on_log=logged,on_exit=lambda code:self.game_exit.emit(code))
            if job.cancel.is_set():process.stop();raise RuntimeError('启动已取消')
            return process
        def done(process):
            self.launch_pending=False;self.process=process;self.instances.record_launch(vid);self.refresh_account()
            if job.cancel.is_set():process.stop();return
            if process.proc.poll() is None:
                self.started_at=time.time();self.status.setText('正在运行 · '+self.instances.display_name(vid))
                if self.config_obj.get('close_after_launch'):self.hide()
        job=self.task('准备启动',work,done)
        if not job:self.launch_pending=False
        else:
            # Any failed preparation must release the UI launch guard.
            original=self.tasks.jobs[job.key]
            failed=original[2]
            def reset(error):self.launch_pending=False;failed(error)
            self.tasks.jobs[job.key]=(original[0],original[1],reset,original[3])

    def install_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle('安装游戏版本');dialog.resize(580,350);body=column(dialog,24,15)
        body.addWidget(label('安装新的游戏版本','title'));body.addWidget(label('原版或加载器将安装到当前游戏库；已有文件会保留。','muted',True))
        form=QFormLayout();game=QComboBox();game.setEditable(True);game.setPlaceholderText('输入 Minecraft 版本，例如 1.21.1')
        loader=QComboBox()
        for text,value in [('原版','vanilla'),('Fabric','fabric'),('Forge','forge'),('NeoForge','neoforge'),('Quilt','quilt'),('OptiFine','optifine')]:loader.addItem(text,value)
        loader_version=QLineEdit();loader_version.setPlaceholderText('留空自动选择最新兼容版本')
        form.addRow('游戏版本',game);form.addRow('加载器',loader);form.addRow('加载器版本',loader_version);body.addLayout(form)
        hint=label('可以直接填写版本号，也可获取官方版本列表。','muted',True);body.addWidget(hint)
        def fetch():
            hint.setText('正在获取版本列表…')
            def done(manifest):
                current=game.currentText();game.clear()
                for entry in manifest.versions[:250]:game.addItem(entry.id)
                if current:game.setCurrentText(current)
                hint.setText('已获取官方版本列表')
            self.tasks.submit(lambda job:self.repo.fetch_manifest(),done,lambda e:hint.setText(str(e)))
        actions=row();actions.addWidget(button('获取版本列表',fetch));actions.addStretch()
        def install():
            version=game.currentText().strip();kind=loader.currentData();build=loader_version.text().strip()
            if not version:hint.setText('请填写或选择游戏版本');return
            repo=self.repo
            def work(job):
                progress=lambda a,b:job.emit((a,b))
                if kind=='vanilla':target=version
                elif kind in ('fabric','quilt'):
                    from ..install.fabric import install_loader
                    target=install_loader(repo,version,build or None,kind,job.emit)
                elif kind=='optifine':
                    from ..install.optifine import install,pick_edition
                    target=install(repo,version,pick_edition(repo.downloader,version,build),on_stage=job.emit,on_progress=progress)
                else:
                    from ..install.forge import install_forge
                    target=install_forge(repo,version,kind,build,job.emit,progress)
                repo.install(target,job.emit,progress);return target
            dialog.accept();self.task('安装 '+version,work,self.installed)
        actions.addWidget(button('安装',install,'primary','download'));body.addLayout(actions);self.dialogs.append(dialog);dialog.open()

    def installed(self,vid):
        self.selected_version=vid;self.config_obj.set('selected_version',vid);self.reload_versions();self.status.setText('已安装 · '+vid)

    def create_instance(self):
        base=self.selected_version
        if not base:self.error('请先选择基础版本');return
        name,ok=QInputDialog.getText(self,'新建独立实例','基础版本：'+base+'\n实例名称')
        if ok and name.strip():self.task('创建独立实例',lambda job:self.repo.create_instance(base,name.strip()),self.installed)

    def import_modpack(self):
        path,_=QFileDialog.getOpenFileName(self,'导入整合包','','整合包 (*.mrpack *.zip)')
        if not path:return
        from ..modpack import import_modpack
        self.task('导入整合包',lambda job:import_modpack(self.repo,Path(path),job.emit,lambda a,b:job.emit((a,b))),self.installed)

    def export_modpack(self,vid):
        path,_=QFileDialog.getSaveFileName(self,'导出 Modrinth 整合包',vid+'.mrpack','整合包 (*.mrpack)')
        if path:
            from ..modpack import export_mrpack
            self.task('导出整合包',lambda job:export_mrpack(self.repo,vid,Path(path)),lambda out:self.status.setText('已导出 · '+str(out)))

    def verify_version(self,vid):
        self.task('校验游戏文件',lambda job:self.repo.verify(vid),
                  lambda problems:QMessageBox.information(self,'校验结果','\n'.join(problems[:30]) if problems else '文件完整。'),False)

    def delete_version(self,vid):
        if QMessageBox.question(self,'移除实例',f'将 {vid} 移入恢复中心？\n文件会保留，可恢复；不会直接删除。')==QMessageBox.StandardButton.Yes:
            self.task('移除实例',lambda job:self.repo.delete_version(vid),lambda _:self.reload_versions())

    def instance_settings(self,vid):
        dialog=QDialog(self);dialog.setWindowTitle('实例设置 · '+vid);dialog.resize(650,610);body=column(dialog,24);form=QFormLayout();fields={}
        meta=self.instances.get(vid);over=self.version_settings.get(vid)
        specs=[('name','显示名称',meta.name),('group','分组',meta.group),('notes','备注',meta.notes)]
        specs += [(key,title,over.get(key,'')) for key,title in [('java_path','Java 路径'),('min_memory','最小内存 MB'),('max_memory','最大内存 MB'),('width','窗口宽度'),('height','窗口高度'),('server_address','服务器'),('jvm_args','JVM 参数'),('game_args','游戏参数')]]
        for key,title,value in specs:
            entry=QLineEdit(str(value));entry.setPlaceholderText('未设置，跟随全局' if key not in ('name','group','notes') else '可选');fields[key]=entry;form.addRow(title,entry)
        for key,title in [('fullscreen','全屏'),('isolate','版本隔离')]:
            combo=QComboBox()
            for text,value in [('跟随全局',None),('开启',True),('关闭',False)]:combo.addItem(text,value)
            combo.setCurrentIndex(combo.findData(over.get(key)));fields[key]=combo;form.addRow(title,combo)
        body.addLayout(form)
        def save():
            try:
                self.repo.assert_idle(vid);values={}
                for key in ('java_path','min_memory','max_memory','width','height','server_address','jvm_args','game_args'):
                    value=fields[key].text().strip()
                    if value:values[key]=int(value) if key in ('min_memory','max_memory','width','height') else value
                for key in ('fullscreen','isolate'):
                    if fields[key].currentData() is not None:values[key]=fields[key].currentData()
                for key, low, high in [('min_memory',512,65536),('max_memory',512,65536),('width',320,7680),('height',240,4320)]:
                    if key in values and not low <= values[key] <= high:
                        raise ValueError(f'{key} 必须在 {low}–{high} 范围内')
                minimum=values.get('min_memory',self.config_obj.get('min_memory'))
                maximum=values.get('max_memory',self.config_obj.get('max_memory'))
                if minimum>maximum:raise ValueError('最小内存不能大于最大内存')
                self.version_settings.set(vid,values);self.instances.update(vid,**{key:fields[key].text().strip() for key in ('name','group','notes')})
                dialog.accept();self.reload_versions()
            except Exception as error:self.error(error)
        body.addWidget(button('保存',save,'primary'));self.dialogs.append(dialog);dialog.open()

    def recovery(self):
        dialog=QDialog(self);dialog.setWindowTitle('恢复中心');dialog.resize(860,480);body=column(dialog,24)
        body.addWidget(label('恢复中心','title'));body.addWidget(label('恢复不会覆盖同名文件，原始位置已存在时会保留回收文件。','muted',True))
        tree=QTreeWidget();tree.setHeaderLabels(['名称','原位置']);tree.setColumnWidth(0,280);body.addWidget(tree,1)
        entries={};repo=self.repo
        def scan(job):
            parents={repo.versions_dir,*(repo.game_dir/name for name in ('mods','saves','resourcepacks','shaderpacks'))}
            for vid in repo.list_installed():parents.update(repo.run_dir(vid)/name for name in ('mods','saves','resourcepacks','shaderpacks'))
            found=[]
            for parent in parents:
                for record in (parent/'.craftbridge-trash').glob('*.recovery.json'):
                    try:
                        data=json.loads(record.read_text(encoding='utf-8'));target=record.with_name(record.name[:-len('.recovery.json')])
                        if target.exists():found.append((target,parent,data['original']))
                    except (OSError,ValueError,KeyError):continue
            return found
        def loaded(found):
            for index,(target,parent,original) in enumerate(found):
                item=QTreeWidgetItem([Path(original).name,original]);item.setData(0,Qt.ItemDataRole.UserRole,index);tree.addTopLevelItem(item);entries[index]=(target,parent)
        self.tasks.submit(scan,loaded,self.error)
        def restore():
            item=tree.currentItem()
            if not item:return
            target,parent=entries[item.data(0,Qt.ItemDataRole.UserRole)]
            from ..safety import restore_recycled
            self.task('恢复文件',lambda job:restore_recycled(target,parent),lambda _: (dialog.accept(),self.reload_versions()))
        body.addWidget(button('恢复所选',restore,'primary'));self.dialogs.append(dialog);dialog.open()
