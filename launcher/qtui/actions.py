"""Qt actions adapt existing launcher services without a second implementation."""
from .lists import FlatTreeWidget as QTreeWidget,DETAIL_ROLE

import json
import shlex
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QComboBox,QInputDialog,QCheckBox,
    QFileDialog,QMessageBox,QTreeWidgetItem)
from .widgets import column,row,label,button,Card
from ..paths import LAUNCHER_VERSION,LAUNCHER_NAME


class Actions:
    def update_mods(self,vid):
        if not self.flush_settings():return
        repo=self.repo
        def work(job):
            from ..modpack import _detect_loader
            from ..mod_plan import updates
            from ..mod_updates import install_selected
            repo.assert_idle(vid);game=repo.resolver.resolve(vid).game_version;loader,_=_detect_loader(repo,vid)
            if not game:raise ValueError('无法识别游戏版本，请先检查实例文件')
            job.emit('检查模组更新')
            selected,unknown=updates(repo.downloader,repo.run_dir(vid)/'mods',game,loader,job)
            return install_selected(repo,vid,selected,job),unknown
        def done(result):
            files,unknown=result
            if self.repo is repo and self.selected_version==vid and self.current_page=='instance' and self.instance_tab=='mods':self.build_mods()
            self.status.setText((f'已更新 {len(files)} 个模组' if files else '未发现可用更新')+(f' · {len(unknown)} 个文件未识别' if unknown else ''))
        def start():
            if self.repo is not repo:self.error('游戏目录已切换，请回到原实例重新检查');return
            return self.task('检查并更新模组',work,done,retry=start,task_repo=repo,task_instance=vid)
        return start()

    def preflight(self,vid):
        from .health_report import HealthReport
        self.show_subpage(HealthReport(self,vid))

    def launch_selected(self):
        if not self.flush_settings():return
        vid=self.selected_version
        if not vid:self.install_dialog();return
        if self.launch_pending or self.process and self.process.proc.poll() is None:self.error('游戏已在运行或启动准备中。');return
        record=self.accounts.current()
        if not record:self.open_accounts();return
        self.launch_pending=True;self.running_version=vid
        self.running_instance_store=self.instances
        repo=self.repo;overrides=self.version_settings.resolve(vid,self.config_obj)
        def work(job):
            from ..launch import Account,LaunchSettings,launch
            from ..java import resolve_java
            from ..preflight import inspect
            job.emit('启动前环境体检')
            issues=inspect(repo,vid,overrides,write_probe=True,cancel=job.cancel,progress=lambda done,total:job.emit(f'检查模组 {done}/{total}'))
            errors=[issue.message for issue in issues if issue.severity=='error']
            if errors:raise RuntimeError('启动前检查发现问题，请在实例管理中打开“环境体检”：\n'+'\n'.join(errors[:12]))
            job.emit('正在验证账号')
            fresh=self.accounts.refresh(record) if record.is_expired() else record
            rv=repo.install(vid,job.emit,lambda a,b:job.emit((a,b)))
            java=resolve_java(rv.java_major,overrides['java_path'],repo.downloader,job.emit,lambda a,b:job.emit((a,b)))
            if not java:raise RuntimeError('未找到可用 Java，请在设置中安装运行时。')
            if job.cancel.is_set():raise RuntimeError('启动已取消')
            injector=''
            local_skin=None
            if fresh.type=='offline':
                from ..skins import SkinLibrary
                local_skin=SkinLibrary(self.root).selected(fresh.uuid)
            authlib_url=fresh.authlib_url
            if local_skin:
                from ..offline_skin import OfflineSkinServer
                job.emit('正在准备本地皮肤')
                self.offline_skin_server=OfflineSkinServer(fresh,*local_skin)
                authlib_url=self.offline_skin_server.url
            if authlib_url:
                job.emit('正在准备外置登录组件')
                from ..auth.authlib import ensure_injector
                injector=str(ensure_injector(repo.downloader,repo.cache_path('authlib-injector.jar')))
            settings=LaunchSettings(java_path=str(java.path),min_memory=overrides['min_memory'],max_memory=overrides['max_memory'],
                width=overrides['width'],height=overrides['height'],fullscreen=overrides['fullscreen'],demo=bool(self.config_obj.get('demo')),
                server_address=overrides['server_address'],extra_jvm_args=shlex.split(overrides['jvm_args']),extra_game_args=shlex.split(overrides['game_args']),process_priority=overrides['process_priority'],pre_launch_command=overrides['pre_launch_command'],post_exit_command=overrides['post_exit_command'],
                launcher_name=LAUNCHER_NAME,launcher_version=LAUNCHER_VERSION,authlib_injector_jar=injector)
            if local_skin:settings.extra_jvm_args.append('-Dauthlibinjector.side=client')
            account=Account(fresh.username,fresh.uuid,fresh.access_token or '0',fresh.user_type,authlib_url,fresh.client_id,fresh.xuid)
            def logged(text,is_error):
                if fresh.access_token and fresh.access_token!='0':text=text.replace(fresh.access_token,'[已隐藏令牌]')
                self.game_log.emit(text,is_error)
            job.emit('正在创建游戏进程')
            process=launch(repo,rv,account,settings,str(java.path),on_log=logged,on_exit=lambda code:self.game_exit.emit(code),cancel=job.cancel)
            if job.cancel.is_set():process.stop();self.stop_offline_skin();raise RuntimeError('启动已取消')
            return process
        def done(process):
            self.launch_pending=False;self.process=process;self.running_instance_store.record_launch(vid);self.refresh_account()
            if job.cancel.is_set():process.stop();return
            if process.proc.poll() is None:
                self.started_at=time.time();self.status.setText('正在运行 · '+self.instances.display_name(vid))
                if self.config_obj.get('show_launch_logs'):self.navigate('logs')
                if self.config_obj.get('close_after_launch'):self.hide()
        job=self.task('准备启动',work,done)
        if not job:self.launch_pending=False
        else:
            # Any failed preparation must release the UI launch guard.
            original=self.tasks.jobs[job.key]
            failed=original[2]
            def reset(error):self.launch_pending=False;self.stop_offline_skin();failed(error)
            self.tasks.jobs[job.key]=(original[0],original[1],reset,original[3])

    def install_dialog(self):
        if not self.flush_settings():return
        from .installer import InstallDialog
        dialog=InstallDialog(self);self.dialogs.append(dialog);self.show_subpage(dialog)

    def installed(self,vid):
        if not (self.instance_editor and self.instance_editor.dirty):
            self.selected_version=vid;self.game_libraries.remember(vid)
        self.reload_versions();self.status.setText('已安装 · '+vid)

    def create_instance(self):
        base=self.selected_version
        if not base:self.error('请先选择基础版本');return
        from ..instance import default_instance_name
        from ..modpack import _base_version,_detect_loader
        suggested=default_instance_name(_base_version(self.repo,base),_detect_loader(self.repo,base)[0] or 'vanilla')
        name,ok=QInputDialog.getText(self,'新建独立实例','基础版本：'+base+'\n实例名称',text=suggested)
        if ok and name.strip():self.task('创建独立实例',lambda job:self.repo.create_instance(base,name.strip()),self.installed)

    def rename_instance(self,vid):
        dialog=QDialog(self);dialog.setWindowTitle('重命名实例');body=column(dialog,24,16)
        body.addWidget(label('实例名称','heading'));field=QLineEdit(self.instances.display_name(vid));body.addWidget(field)
        hint=label('更改展示名称，游戏目录和存档位置保持不变。','muted');body.addWidget(hint)
        def save():
            name=field.text().strip()
            if not name:hint.setText('请输入实例名称');return
            self.instances.update(vid,name=name);self.update_selection()
            if self.selected_version==vid and self.current_page=='instance':self.page_title='实例管理 · '+name
            self.reload_versions(refresh_page=False);dialog.accept()
            if self.current_page=='versions':self.build_versions()
            self.status.setText('实例已重命名 · '+name)
        actions=row();actions.addStretch();actions.addWidget(button('取消',dialog.reject));actions.addWidget(button('保存',save,'primary'));body.addLayout(actions);body.addStretch()
        self.show_subpage(dialog);field.selectAll();field.setFocus()

    def clone_instance(self,vid):
        name,ok=QInputDialog.getText(self,'复制实例','新实例名称',text=self.instances.display_name(vid)+'-副本')
        if not ok or not name.strip():return
        repo=self.repo;store=self.instances;settings=self.version_settings;meta=store.get(vid)
        overrides=settings.get(vid)
        def work(job):return repo.clone_instance(vid,name.strip(),job.cancel,job.emit)
        def done(new_id):
            store.update(new_id,name=name.strip(),group=meta.group,notes=meta.notes,icon=meta.icon,tags=list(meta.tags))
            if overrides:settings.set(new_id,{**overrides,'isolate':True})
            if self.repo is repo:self.installed(new_id)
            else:self.status.setText('实例已复制 · '+new_id)
        self.task('复制实例',work,done,task_repo=repo,task_instance=vid)

    def set_instance_icon(self,vid):
        path,_=QFileDialog.getOpenFileName(self,'选择实例图标','','图片 (*.png *.jpg *.jpeg *.webp)')
        if not path:return
        try:
            from hashlib import sha256
            from PySide6.QtGui import QImageReader
            source=Path(path)
            if source.stat().st_size>5*1024*1024:raise ValueError('图片不能超过 5 MiB')
            reader=QImageReader(str(source));size=reader.size()
            if not size.isValid() or size.width()>4096 or size.height()>4096:raise ValueError('图片无效或尺寸过大')
            reader.setScaledSize(size.scaled(256,256,Qt.AspectRatioMode.KeepAspectRatio));image=reader.read()
            if image.isNull():raise ValueError('无法读取图片')
            image=image.scaled(256,256,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            digest=sha256(source.read_bytes()).hexdigest()
            folder=self.root/'.onion'/'instance-icons';folder.mkdir(parents=True,exist_ok=True)
            output=folder/(digest+'.png')
            if not output.exists() and not image.save(str(output),'PNG'):raise OSError('无法保存图标')
            self.instances.update(vid,icon=str(Path('.onion')/'instance-icons'/output.name))
            if self.current_page=='versions':self.build_versions()
            self.status.setText('实例图标已更新')
        except Exception as error:self.error(error)

    def reset_instance_icon(self,vid):
        self.instances.update(vid,icon='')
        if self.current_page=='versions':self.build_versions()
        self.status.setText('已恢复默认图标')

    def import_modpack(self):
        path,_=QFileDialog.getOpenFileName(self,'导入整合包','','整合包 (*.mrpack *.zip)')
        if not path:return
        from ..modpack import import_modpack
        self.task('导入整合包',lambda job:import_modpack(self.repo,Path(path),job.emit,lambda a,b:job.emit((a,b))),self.installed)

    def export_modpack(self,vid):
        dialog=QDialog(self);dialog.setWindowTitle('导出整合包');dialog.navigation_title='导出整合包'
        body=column(dialog,24,12);fields=row();name=QLineEdit(self.instances.display_name(vid));name.setPlaceholderText('整合包名称')
        version=QLineEdit('1.0');version.setPlaceholderText('版本号');version.setMaximumWidth(180);fields.addWidget(name,1);fields.addWidget(version);body.addLayout(fields)
        choices={}
        for title,keys,default in [('模组',('mods',),True),('配置',('config',),True),('资源包',('resourcepacks',),True),('光影',('shaderpacks',),True),('脚本',('kubejs','scripts'),True),('游戏设置',('options.txt','optionsof.txt','optionsshaders.txt'),True),('服务器列表',('servers.dat',),False),('世界存档',('saves',),False)]:
            box=QCheckBox(title);box.setChecked(default);choices[box]=keys;body.addWidget(box)
        body.addStretch();actions=row();actions.addStretch();actions.addWidget(button('取消',dialog.reject))
        repo=self.repo
        def export():
            pack_name=name.text().strip();pack_version=version.text().strip()
            if not pack_name or not pack_version:self.status.setText('请输入整合包名称和版本号');return
            path,_=QFileDialog.getSaveFileName(dialog,'导出 Modrinth 整合包',pack_name+'.mrpack','整合包 (*.mrpack)')
            if not path:return
            from ..modpack import export_mrpack
            selected=[item for box,items in choices.items() if box.isChecked() for item in items]
            def work(job):
                repo.assert_idle(vid)
                return export_mrpack(repo,vid,Path(path),pack_name,pack_version=pack_version,selected=selected,cancel=job.cancel,progress=job.emit)
            if self.task('导出整合包',work,lambda out:self.status.setText('已导出 · '+str(out)),task_repo=repo,task_instance=vid):dialog.accept()
        actions.addWidget(button('导出',export,'primary','download'));body.addLayout(actions);self.show_subpage(dialog)

    def verify_version(self,vid):
        self.task('校验游戏文件',lambda job:self.repo.verify(vid),
                  lambda problems:QMessageBox.information(self,'校验结果','\n'.join(problems[:30]) if problems else '文件完整。'),False)

    def delete_version(self,vid):
        if QMessageBox.question(self,'移除实例',f'将 {vid} 移入恢复中心？\n文件会保留，可恢复；不会直接删除。')==QMessageBox.StandardButton.Yes:
            self.task('移除实例',lambda job:self.repo.delete_version(vid),lambda _:self.reload_versions())

    def instance_settings(self,vid):
        if not self.set_selected(vid):return
        self.instance_tab='game';self.navigate('instance')

    def recovery(self):
        dialog=QDialog(self);dialog.setWindowTitle('恢复中心');dialog.resize(860,480);body=column(dialog,24)
        tree=QTreeWidget();tree.entities();body.addWidget(tree,1)
        entries={};repo=self.repo
        def scan(job):
            import os
            parents={repo.versions_dir,*(repo.game_dir/name for name in ('mods','saves','resourcepacks','shaderpacks','screenshots','schematics'))}
            for vid in repo.list_installed():parents.update(repo.run_dir(vid)/name for name in ('mods','saves','resourcepacks','shaderpacks','screenshots','schematics'))
            for saves in tuple(parent for parent in parents if parent.name=='saves' and parent.is_dir()):
                for world in saves.iterdir():
                    if world.is_dir() and not world.is_symlink() and not world.is_junction():parents.add(world/'datapacks')
            for root in tuple(parent for parent in parents if parent.name in ('screenshots','schematics') and parent.is_dir()):
                for index,(folder,dirs,_) in enumerate(os.walk(root,followlinks=False)):
                    if index>=20000:break
                    current=Path(folder)
                    if '.craftbridge-trash' in dirs:parents.add(current)
                    dirs[:]=[d for d in dirs if not d.startswith('.') and not (current/d).is_symlink() and not (current/d).is_junction()]
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
                item=QTreeWidgetItem([Path(original).name]);item.setData(0,DETAIL_ROLE,original);item.setToolTip(0,original);item.setData(0,Qt.ItemDataRole.UserRole,index);tree.addTopLevelItem(item);entries[index]=(target,parent)
        self.tasks.submit(scan,loaded,self.error)
        def restore():
            item=tree.currentItem()
            if not item:return
            target,parent=entries[item.data(0,Qt.ItemDataRole.UserRole)]
            from ..safety import restore_recycled
            self.task('恢复文件',lambda job:restore_recycled(target,parent),lambda _: (dialog.accept(),self.reload_versions()))
        body.addWidget(button('恢复所选',restore,'primary'));self.dialogs.append(dialog);dialog.open()
