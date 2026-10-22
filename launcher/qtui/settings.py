"""Grouped, draft-based settings shared by the launcher and individual instances."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QStackedWidget,QLineEdit,QComboBox,QSpinBox,
    QCheckBox,QFileDialog,QMessageBox,QDialog,QColorDialog)
from PySide6.QtGui import QColor
from .widgets import Page,SettingsSection as Card,ToggleSwitch,InlineSpinBox,SettingsComboBox,themed_style,column,row,label,button,setting_row,icon


class SettingsEditor(QWidget):
    def __init__(self,window,version_id=None,flat=False,external_nav=False):
        super().__init__();self.launcher=window;self.vid=version_id;self.fields={};self.overrides={};self.flat=flat;self.custom_controls=[]
        self.values=window.version_settings.get(version_id) if version_id else window.config_obj.data.copy()
        self.dirty=False
        outer=column(self,0,15);layout=row(spacing=20);outer.addLayout(layout,1)
        menu=QWidget();menu.setFixedWidth(156);nav=column(menu,0,5)
        if not flat and not external_nav:layout.addWidget(menu)
        else:menu.hide();menu.setParent(self)
        self.stack=QStackedWidget();layout.addWidget(self.stack,1);self.tabs=[]
        self.tab_names={};self.game_body=None
        if flat:
            self.specific=QCheckBox('启用实例特定游戏设置');self.specific.setChecked(bool(self.values))
            outer.insertWidget(0,self.specific)
        def tab(title,glyph):
            if (flat or title in ('游戏与窗口','高级参数')) and self.game_body is not None:return self.game_body
            page=Page();index=self.stack.addWidget(page)
            self.tab_names[title]=index
            item=button(title,lambda:self.select_tab(index),'nav',glyph);item.setCheckable(True)
            nav.addWidget(item);self.tabs.append(item)
            if title=='全局游戏设置' or flat:self.game_body=page.body
            return page.body
        if version_id and not flat:
            body=tab('实例信息','grid');meta=window.instances.get(version_id)
            card=Card('让这个实例属于你','展示信息不会修改版本文件名。')
            for key,title,value in [('name','显示名称',meta.name),('group','分组',meta.group),('notes','备注',meta.notes)]:
                edit=QLineEdit(value);edit.setPlaceholderText(version_id if key=='name' else '可选');edit.textChanged.connect(self.mark_dirty);self.fields[key]=edit;setting_row(card.body,title,'仅保存在当前启动器',edit)
            body.addWidget(card)
            tools=Card('实例维护',version_id)
            for title,callback,glyph in [('打开实例目录',lambda:window.open_folder(window.repo.run_dir(version_id)),'folder'),('校验游戏文件',lambda:window.verify_version(version_id),'package'),('导出整合包',lambda:window.export_modpack(version_id),'download')]:tools.body.addWidget(button(title,callback,'soft',glyph))
            body.addWidget(tools)
        body=tab('全局游戏设置' if not version_id else '游戏设置','java')
        card=Card('Java 运行环境','留空时，启动器会根据游戏版本选择或下载匹配的 Java。')
        self.edit(card,'java_path','Java 路径','选择 java.exe 或 javaw.exe','自动选择兼容的 Java',browse='file')
        java_manager=button('检测 / 下载 Java',lambda:window.manage_java(self.java_chosen),'soft','java');self.custom_controls.append(java_manager)
        setting_row(card.body,'Java 管理','查找本机 Java 或下载官方运行时',java_manager);body.addWidget(card)
        card=Card('内存分配','单位为 MiB。大型整合包可以增加上限，请为系统保留足够内存。')
        self.check(card,'auto_memory','自动分配内存','根据物理内存选择保守的分配值')
        self.spin(card,'min_memory','最小内存','JVM 初始堆内存',512,65536,256)
        self.spin(card,'max_memory','最大内存','JVM 最大堆内存',512,65536,256)
        from ..memory import recommended_memory
        initial,maximum=recommended_memory()
        recommendation=label(f'初始 {initial:,} MiB / 最大 {maximum:,} MiB','muted')
        setting_row(card.body,'自动分配参考','根据当前系统可用物理内存估算',recommendation)
        def memory_state():
            auto=(self.fields['auto_memory'].isChecked() if not self.vid or self.flat or self.overrides['auto_memory'].isChecked() else bool(window.config_obj.get('auto_memory')))
            for key in ('min_memory','max_memory'):
                field=self.fields[key];field.setEnabled(not auto and (self.specific.isChecked() if self.flat else not self.vid or self.overrides[key].isChecked()))
        self.fields['auto_memory'].toggled.connect(memory_state)
        self.update_memory_controls=memory_state
        if self.vid and not flat:self.overrides['auto_memory'].toggled.connect(memory_state)
        for key in ('min_memory','max_memory'):
            if key in self.overrides:self.overrides[key].toggled.connect(memory_state)
        memory_state();body.addWidget(card)
        body=tab('游戏与窗口','world');card=Card('游戏窗口','实例可以继承全局设置，也可以独立指定。')
        for key,title,low,high in [('width' if version_id else 'window_width','窗口宽度',320,7680),('height' if version_id else 'window_height','窗口高度',240,4320)]:self.spin(card,key,title,'以游戏逻辑像素为单位',low,high,1)
        preset=SettingsComboBox();preset.addItem('选择窗口尺寸',None)
        for title,value in [('1280 × 720',(1280,720)),('1600 × 900',(1600,900)),('1920 × 1080',(1920,1080))]:preset.addItem(title,value)
        def resize_preset(index):
            size=preset.currentData()
            if not size:return
            for key,value in zip(('width','height') if self.vid else ('window_width','window_height'),size):
                if key in self.overrides:self.overrides[key].setChecked(True)
                self.fields[key].setValue(value)
        preset.currentIndexChanged.connect(resize_preset);self.custom_controls.append(preset);setting_row(card.body,'常用尺寸','选择后更新窗口宽度与高度',preset)
        self.check(card,'fullscreen','全屏启动','使用游戏原生全屏模式');body.addWidget(card)
        card=Card('运行目录与快速加入')
        if not version_id:self.edit(card,'game_dir','游戏库目录','修改目录不会移动已有游戏文件',str(window.repo.game_dir),browse='directory')
        self.check(card,'isolate' if version_id else 'version_isolation','版本隔离','将模组、存档与配置保存在各自的实例目录')
        self.edit(card,'server_address','自动加入服务器','启动后连接指定服务器；留空进入主菜单','例如 play.example.com:25565');body.addWidget(card)
        if not version_id:
            body=tab('下载与网络','download');card=Card('下载设置','修改后会用于后续下载任务。')
            self.combo(card,'download_source','下载源','游戏与资源文件的下载服务',[('Mojang 官方','mojang'),('BMCLAPI 镜像','bmclapi')])
            self.spin(card,'max_download_threads','并发下载数','同时进行的文件下载数量',1,32,1)
            self.spin(card,'download_speed_limit','下载限速','单位 KiB/s；0 表示不限速',0,100000,256);body.addWidget(card)
            card=Card('代理连接','留空时直连。仅影响启动器网络请求。')
            self.edit(card,'proxy_host','代理主机','HTTP 代理服务器地址','例如 127.0.0.1')
            self.spin(card,'proxy_port','代理端口','0 表示不启用代理',0,65535,1);body.addWidget(card)
            body=tab('启动器行为','home');card=Card('启动与退出')
            self.check(card,'close_after_launch','启动后收起窗口','游戏启动成功后隐藏启动器')
            self.check(card,'keep_launcher_open','游戏退出后保留启动器','关闭此项会在游戏退出后结束启动器')
            self.check(card,'show_launch_logs','启动后显示日志页','便于查看游戏输出和定位问题');body.addWidget(card)
            card=Card('账号管理','正版、离线与外置账号在统一的账号窗口中管理。')
            card.body.addWidget(button('管理游戏账号',window.open_accounts,'soft','account'));body.addWidget(card)
            body=tab('外观','grid');card=Card('特征色','用于高亮设置行中可点击或编辑的文字。')
            self.edit(card,'accent_color','高亮颜色','输入六位十六进制颜色，例如 #cebafa','#cebafa')
            if not self.fields['accent_color'].text():self.fields['accent_color'].setText('#cebafa')
            def choose_accent():
                color=QColorDialog.getColor(QColor(self.fields['accent_color'].text()),self,'选择特征色')
                if color.isValid():self.fields['accent_color'].setText(color.name())
            setting_row(card.body,'颜色选择器','选择后保存设置生效',button('选择颜色',choose_accent,'soft'));body.addWidget(card)
            card=Card('首页背景','选择本地图片，首页将按窗口比例裁切显示。')
            field=QLineEdit(str(self.initial('background_image') or ''));field.setPlaceholderText('使用默认背景');self.add(card,'background_image','自定义图片','支持 PNG、JPG 和 WebP',field)
            def choose_background():
                path,_=QFileDialog.getOpenFileName(self,'选择首页背景','','图片 (*.png *.jpg *.jpeg *.webp)')
                if path:field.setText(path)
            actions=row();actions.addWidget(button('选择图片',choose_background,'soft','folder'));actions.addWidget(button('恢复默认',lambda:field.clear()));actions.addStretch();card.body.addLayout(actions);body.addWidget(card)
        body=tab('高级参数','settings');card=Card('启动参数','通常保持默认即可。额外参数会传递给 Java 或游戏。')
        self.edit(card,'jvm_args','JVM 参数','支持用引号包裹含空格的参数','留空使用默认参数')
        self.edit(card,'game_args','游戏参数','附加到游戏启动命令','留空使用默认参数')
        if not version_id:self.check(card,'demo','试玩模式','仅在需要 Minecraft 试玩时开启')
        body.addWidget(card)
        nav.addStretch();self.select_tab(0)
        bar=row();self.hint=label('更改在保存后生效','muted');bar.addWidget(self.hint,1)
        if version_id and not flat:bar.addWidget(button('全部跟随全局',self.inherit_all))
        self.save_button=button('保存设置',self.save,'primary');bar.addWidget(self.save_button);outer.addLayout(bar)
        if flat:
            def enable_controls(checked):
                for field in list(self.fields.values())+self.custom_controls:field.setEnabled(checked)
                memory_state()
            def specific_changed(checked):
                enable_controls(checked);self.mark_dirty()
                self.hint.setText('使用实例独立配置，保存后生效' if checked else '保存后将恢复使用全局游戏设置')
            self.specific.toggled.connect(specific_changed)
            enable_controls(self.specific.isChecked())
            self.hint.setText('当前使用实例特定设置' if self.specific.isChecked() else '当前跟随全局游戏设置；勾选上方选项后可独立调整')

    def select_tab(self,index):
        self.stack.setCurrentIndex(index)
        for i,item in enumerate(self.tabs):item.setChecked(i==index)

    def mark_dirty(self,*args):
        self.dirty=True
        if hasattr(self,'hint'):self.hint.setText('有未保存的更改')

    def initial(self,key):
        if key in self.values:return self.values[key]
        translated={'width':'window_width','height':'window_height','isolate':'version_isolation'}
        return self.launcher.config_obj.get(translated.get(key,key))

    def add(self,card,key,title,description,field):
        field.setObjectName('setting_'+key);self.fields[key]=field
        if self.vid and not self.flat:
            field.setMinimumWidth(220);field.setMaximumWidth(310)
            holder=column(spacing=5);holder.addWidget(field)
            override=QCheckBox('单独设置');override.setChecked(key in self.values);self.overrides[key]=override
            field.setEnabled(override.isChecked());override.toggled.connect(field.setEnabled);override.toggled.connect(self.mark_dirty);holder.addWidget(override)
            def inherit(checked):
                if checked:return
                translated={'width':'window_width','height':'window_height','isolate':'version_isolation'}
                value=self.launcher.config_obj.get(translated.get(key,key))
                if isinstance(field,QCheckBox):field.setChecked(bool(value))
                elif isinstance(field,QSpinBox):field.setValue(int(value or 0))
                elif isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
                else:field.setText(str(value or ''))
            override.toggled.connect(inherit)
            setting_row(card.body,title,description,holder)
        else:setting_row(card.body,title,description,field)
        if isinstance(field,QCheckBox):field.toggled.connect(self.mark_dirty)
        elif isinstance(field,QSpinBox):field.valueChanged.connect(self.mark_dirty)
        elif isinstance(field,QComboBox):field.currentIndexChanged.connect(self.mark_dirty)
        else:field.textChanged.connect(self.mark_dirty)

    def edit(self,card,key,title,description,placeholder,browse=None):
        field=QLineEdit(str(self.initial(key) or ''));field.setPlaceholderText(placeholder)
        self.add(card,key,title,description,field)
        if browse:
            def choose():
                path=(QFileDialog.getExistingDirectory(self,'选择游戏库',field.text()) if browse=='directory' else QFileDialog.getOpenFileName(self,'选择 Java',field.text(),'Java (java.exe javaw.exe);;所有文件 (*)')[0])
                if path:
                    if key in self.overrides:self.overrides[key].setChecked(True)
                    field.setText(path)
            action=field.addAction(icon('folder'),QLineEdit.ActionPosition.TrailingPosition);action.setToolTip('浏览目录' if browse=='directory' else '浏览 Java');action.triggered.connect(choose)

    def spin(self,card,key,title,description,low,high,step):
        field=InlineSpinBox();field.setRange(low,high);field.setSingleStep(step);field.setValue(int(self.initial(key) or 0))
        self.add(card,key,title,description,field)

    def check(self,card,key,title,description):
        field=ToggleSwitch();field.setChecked(bool(self.initial(key)));self.add(card,key,title,description,field)

    def combo(self,card,key,title,description,options):
        field=SettingsComboBox()
        for text,value in options:field.addItem(text,value)
        index=field.findData(self.initial(key))
        if index<0:field.addItem('当前配置（保留）',self.initial(key));index=field.count()-1
        field.setCurrentIndex(index);self.add(card,key,title,description,field)

    def inherit_all(self):
        for box in self.overrides.values():box.setChecked(False)
        self.mark_dirty()

    def java_chosen(self,path):
        if 'java_path' in self.overrides:self.overrides['java_path'].setChecked(True)
        self.fields['java_path'].setText(str(path))

    def refresh_inherited(self):
        if not self.flat or self.specific.isChecked() or self.dirty:return
        translated={'width':'window_width','height':'window_height','isolate':'version_isolation'}
        for key,field in self.fields.items():
            value=self.launcher.config_obj.get(translated.get(key,key));previous=field.blockSignals(True)
            try:
                if isinstance(field,QCheckBox):field.setChecked(bool(value))
                elif isinstance(field,QSpinBox):field.setValue(int(value or 0))
                else:field.setText(str(value or ''))
            finally:field.blockSignals(previous)
        self.update_memory_controls()

    def save(self):
        w=self.launcher
        try:
            if w.mutating or w.launch_pending:raise ValueError('请先结束当前文件操作或启动任务，再保存设置。')
            values={}
            for key,field in self.fields.items():
                if key in self.overrides and not self.overrides[key].isChecked():continue
                values[key]=(field.isChecked() if isinstance(field,QCheckBox) else field.value() if isinstance(field,QSpinBox) else field.currentData() if isinstance(field,QComboBox) else field.text().strip())
            minimum=values.get('min_memory',w.config_obj.get('min_memory'));maximum=values.get('max_memory',w.config_obj.get('max_memory'))
            if not (self.flat and not self.specific.isChecked()) and not values.get('auto_memory',w.config_obj.get('auto_memory')) and minimum>maximum:raise ValueError('最小内存不能大于最大内存。')
            if not self.vid and bool(values.get('proxy_host')) != bool(values.get('proxy_port')):raise ValueError('代理主机和端口需要同时填写，或同时留空 / 设为 0。')
            if not self.vid:
                import re
                if not re.fullmatch(r'#[0-9a-fA-F]{6}',values.get('accent_color','')):raise ValueError('特征色需要使用 #RRGGBB 格式。')
            if self.vid:
                w.repo.assert_idle(self.vid)
                metadata={key:values.pop(key) for key in ('name','group','notes') if key in values}
                if self.flat and not self.specific.isChecked():values={}
                w.version_settings.set(self.vid,values)
                if metadata:w.instances.update(self.vid,**metadata)
            else:
                w.config_obj.update(values)
                w.setStyleSheet(themed_style(values['accent_color']))
                from ..repository import GameRepository
                w.repo=GameRepository(w.config_obj)
            self.dirty=False;self.hint.setText('设置已保存');w.status.setText('设置已保存')
            # Update selectors without rebuilding this editor and losing its category.
            w.reload_versions(refresh_page=False)
        except Exception as error:w.error(error)


class InstanceSettingsDialog(QDialog):
    def __init__(self,window,vid):
        super().__init__(window);self.setWindowTitle('实例设置 · '+window.instances.display_name(vid));self.resize(1020,760);self.setMinimumSize(850,620)
        body=column(self,24,18);body.addWidget(label(window.instances.display_name(vid),'title'))
        body.addWidget(label('实例设置  /  未单独设置的项目将跟随全局配置','muted'))
        self.editor=SettingsEditor(window,vid);body.addWidget(self.editor,1)

    def reject(self):
        if self.editor.dirty and QMessageBox.question(self,'尚未保存','放弃未保存的实例设置？')!=QMessageBox.StandardButton.Yes:return
        super().reject()
