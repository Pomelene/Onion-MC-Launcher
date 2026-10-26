"""Grouped settings with debounced, validated automatic persistence."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QStackedWidget,QLineEdit,QComboBox,QSpinBox,
    QCheckBox,QFileDialog,QMessageBox,QDialog,QSlider)
from PySide6.QtGui import QColor,QFontDatabase
from .widgets import Page,SettingsSection as Card,ToggleSwitch,InlineSpinBox,SettingsComboBox,column,row,label,button,setting_row,icon
from .theme import paint_color,APPEARANCE_KEYS,effective_accent


class SettingsSlider(QSlider):
    """Let the surrounding page scroll until this editor is explicitly focused."""
    def __init__(self,*args):
        super().__init__(*args);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self,event):
        if not self.hasFocus():event.ignore();return
        super().wheelEvent(event)


class SettingsEditor(QWidget):
    def __init__(self,window,version_id=None,flat=False,external_nav=False):
        super().__init__();self.launcher=window;self.vid=version_id;self.fields={};self.overrides={};self.flat=flat;self.custom_controls=[]
        self.version_store=window.version_settings;self.meta_store=window.instances
        self.values=window.version_settings.get(version_id) if version_id else window.config_obj.data.copy()
        self.dirty=False
        self.sliders={}
        self.unit_labels={};self.number_hints={};self.numeric_holders={}
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(33)
        self.preview_timer.timeout.connect(self.preview_transparency)
        self.ready=False
        self.autosave_timer=QTimer(self);self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(450);self.autosave_timer.timeout.connect(self._autosave)
        outer=column(self,0,15);layout=row(spacing=20);outer.addLayout(layout,1)
        menu=QWidget();menu.setFixedWidth(156);nav=column(menu,0,5)
        if not flat and not external_nav:layout.addWidget(menu)
        else:menu.hide();menu.setParent(self)
        self.stack=QStackedWidget();layout.addWidget(self.stack,1);self.tabs=[]
        self.tab_names={};self.game_body=None
        if flat:
            scope=QWidget();scope_body=column(scope,0,6)
            self.specific=QCheckBox('仅为当前实例启用独立设置');self.specific.setChecked(bool(self.values))
            scope_body.addWidget(self.specific)
            self.scope_description=label('','muted',True);scope_body.addWidget(self.scope_description)
            self.global_settings_button=button('设置 → 全局游戏设置',self.open_global_settings,'soft','settings')
            scope_body.addWidget(self.global_settings_button,0,Qt.AlignmentFlag.AlignLeft)
            outer.insertWidget(0,scope)
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
        body.addWidget(card)
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
            self.number_slider(card,'max_download_threads','并发下载数','同时进行的文件下载数量',1,32,' 个')
            self.spin(card,'download_speed_limit','下载限速','单位 KiB/s；0 表示不限速',0,100000,256)
            body.addWidget(card)
            card=Card('代理连接','留空时直连。仅影响启动器网络请求。')
            self.edit(card,'proxy_host','代理主机','HTTP 代理服务器地址','例如 127.0.0.1')
            self.spin(card,'proxy_port','代理端口','0 表示不启用代理',0,65535,1);body.addWidget(card)
            body=tab('启动器行为','home');card=Card('启动与退出')
            self.check(card,'close_after_launch','启动后收起窗口','游戏启动成功后隐藏启动器')
            self.check(card,'keep_launcher_open','游戏退出后保留启动器','关闭此项会在游戏退出后结束启动器')
            self.check(card,'show_launch_logs','启动后显示日志页','便于查看游戏输出和定位问题');body.addWidget(card)
            card=Card('启动器更新')
            self.check(card,'check_launcher_updates','启动时检查更新','仅提示当前版本系列的新版本')
            from ..paths import LAUNCHER_VERSION
            setting_row(card.body,'当前版本','',button(LAUNCHER_VERSION+' · 版本管理',window.updater.manage_versions,'soft','refresh'))
            body.addWidget(card)
            card=Card('账号管理','正版、离线与外置账号在统一的账号窗口中管理。')
            card.body.addWidget(button('管理游戏账号',window.open_accounts,'soft','account'));body.addWidget(card)
            body=tab('外观','grid');card=Card('界面外观','透明度越高，显示越淡；修改后自动保存。')
            self.combo(card,'color_mode','显示模式','切换启动器的深色或浅色外观',[('跟随系统','auto'),('深色','dark'),('浅色','light')])
            self.check(card,'bold_text','粗体文字','加粗启动器界面文字');self.fields['bold_text'].toggled.connect(self.queue_preview)
            for key,title,description,high in [
                ('text_transparency','文字透明度','0% 为不透明，最高 70%，保留基本可读性',70),
                ('ui_transparency','UI 透明度','仅调整界面底色和控件，不影响背景图片；文字透明度独立控制',90)]:
                self.percentage(card,key,title,description,high)
            body.addWidget(card)
            card=Card('字体与可读性')
            families=QFontDatabase.families()
            self.combo(card,'font_family','界面字体','使用系统已有字体，不随程序打包字体',[('默认（Microsoft YaHei UI）','')]+[(name,name) for name in families])
            self.number_slider(card,'font_size','界面字号','同时调整标题、列表和辅助文字，12–18 逻辑像素',12,18,'px',preview=True)
            self.combo(card,'font_antialiasing','字体抗锯齿','自动通常最适合当前显示器',[('自动','auto'),('灰度','gray'),('子像素（由系统支持情况决定）','subpixel')])
            self.combo(card,'log_font_family','日志字体','仅影响运行日志',[('默认（Consolas）','Consolas'),('跟随界面字体','')]+[(name,name) for name in families if name!='Consolas'])
            self.number_slider(card,'log_font_size','日志字号','独立于界面字号',9,28,'px',preview=True)
            sample=label('字体预览 · 清华联盟工坊 · Onion 0123456789','muted',True)
            sample.setContentsMargins(16,10,16,10);card.body.addWidget(sample)
            body.addWidget(card)
            card=Card('配色','以感知色彩空间生成界面底色、选中态与文字颜色。')
            self.combo(card,'accent_source','颜色来源','壁纸取色失败时使用默认紫色',[('自定义颜色','custom'),('跟随背景壁纸','wallpaper')])
            self.combo(card,'color_style','色彩模式','改变配色的饱和度与色相；保真尽量保留原色',[
                ('保真','fidelity'),('柔和点缀','tonal_spot'),('鲜艳','vibrant'),('中性','neutral'),('水果沙拉','fruit_salad'),('彩虹','rainbow')])
            self.edit(card,'accent_color','自定义颜色','输入六位十六进制颜色，例如 #cebafa','#cebafa')
            if not self.fields['accent_color'].text():self.fields['accent_color'].setText('#cebafa')
            def choose_accent():
                from .color_picker import ColorPicker
                picker=ColorPicker(QColor(self.fields['accent_color'].text()),self)
                if picker.exec()==QDialog.DialogCode.Accepted:
                    self.fields['accent_color'].setText(picker.color.name())
                    self.fields['accent_source'].setCurrentIndex(self.fields['accent_source'].findData('custom'))
            self.choose_accent_button=button('选择颜色',choose_accent,'soft')
            setting_row(card.body,'颜色选择器','选择颜色后改用自定义颜色',self.choose_accent_button)
            self.palette_feedback=label('','',True);self.palette_feedback.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            setting_row(card.body,'当前主题色','壁纸取色只改变界面配色，不会改变背景图片',self.palette_feedback)
            self.fields['accent_source'].currentIndexChanged.connect(self.refresh_color_feedback)
            body.addWidget(card)
            card=Card('布局与动效')
            self.check(card,'titlebar_transparent','标题栏透明','关闭后标题栏保持不透明；背景与正文控件仍独立控制')
            self.number_slider(card,'corner_radius','圆角大小','控件和弹出选择框的圆角；滑块、开关保留圆形结构',0,24,'px',preview=True)
            self.number_slider(card,'animation_duration','动画时长','控制悬停、按压与开关动效；0 表示关闭，导航尾随按比例变化',0,600,'ms',preview=True)
            self.check(card,'ui_animations','界面动效','导航胶囊滑动、按钮按压和开关滑动；关闭可减少动态效果');body.addWidget(card)
            card=Card('首页背景','独立设置背景显示方式与透明度，不改变首页按钮和文字。')
            self.combo(card,'background_scope','背景范围','整个窗口会将背景延伸至导航栏和标题栏',[
                ('仅主页内容区','content'),('整个窗口（含导航栏）','window')])
            self.combo(card,'background_mode','图片显示方式','填充会裁切，适应会保留完整图片',[
                ('填充（保持比例，裁切）','fill'),('自适应（完整显示）','fit'),
                ('拉伸（铺满）','stretch'),('居中（原始大小）','center'),('平铺','tile')])
            self.number_slider(card,'background_blur','背景图片模糊','只处理背景图片，文字和控件保持清晰；0 为关闭',0,40,'px',preview=True)
            self.percentage(card,'background_transparency','背景透明度','0% 为完整显示；100% 为隐藏图片及装饰',100)
            field=QLineEdit(str(self.initial('background_image') or ''));field.setPlaceholderText('使用默认背景');field.setProperty('wideEditor',True);self.add(card,'background_image','自定义图片','支持 PNG、JPG 和 WebP',field)
            def choose_background(background_field=field):
                path,_=QFileDialog.getOpenFileName(self,'选择首页背景','','图片 (*.png *.jpg *.jpeg *.webp)')
                if path:background_field.setText(path)
            picture_actions=QWidget();actions=row(picture_actions,0,12)
            for title,callback,glyph in [('选择图片',choose_background,'folder'),('恢复默认',lambda background_field=field:background_field.clear(),None)]:
                action=button(title,callback,'soft',glyph);action.setProperty('settingAction',True);action.setMinimumWidth(112);actions.addWidget(action)
            setting_row(card.body,'图片操作','',picture_actions);body.addWidget(card)
            card=Card('首页欢迎语')
            self.check(card,'custom_home_welcome','自定义主界面欢迎字样','默认不显示；开启后显示下方自定义内容')
            self.edit(card,'home_welcome_large','大字','','输入欢迎语；留空不显示')
            self.edit(card,'home_welcome_small','小字','','输入欢迎语；留空不显示')
            for key in ('home_welcome_large','home_welcome_small'):self.fields[key].setMaxLength(120)
            def preview_welcome(*args):
                custom=self.fields['custom_home_welcome'].isChecked()
                for key in ('home_welcome_large','home_welcome_small'):self.fields[key].setEnabled(custom)
                window.update_home_welcome({
                    'custom_home_welcome':custom,
                    'home_welcome_large':self.fields['home_welcome_large'].text().strip(),
                    'home_welcome_small':self.fields['home_welcome_small'].text().strip()})
            self.fields['custom_home_welcome'].toggled.connect(preview_welcome)
            for key in ('home_welcome_large','home_welcome_small'):self.fields[key].textChanged.connect(preview_welcome)
            preview_welcome();body.addWidget(card)
            reset=button('恢复外观默认值',self.reset_appearance,'soft')
            body.addWidget(reset,0,Qt.AlignmentFlag.AlignRight)
        body=tab('高级参数','settings');card=Card('启动参数','通常保持默认即可。额外参数会传递给 Java 或游戏。')
        self.edit(card,'jvm_args','JVM 参数','支持用引号包裹含空格的参数','留空使用默认参数')
        self.edit(card,'game_args','游戏参数','附加到游戏启动命令','留空使用默认参数')
        if not version_id:self.check(card,'demo','试玩模式','仅在需要 Minecraft 试玩时开启')
        body.addWidget(card)
        nav.addStretch();self.select_tab(0)
        if not version_id:
            from .java_manager import JavaManager
            self.java_manager=JavaManager(window);self.tab_names['Java 管理']=self.stack.addWidget(self.java_manager)
            index=self.tab_names['Java 管理'];item=button('Java 管理',lambda:self.select_tab(index),'nav','java')
            item.setCheckable(True);nav.insertWidget(nav.count()-1,item);self.tabs.append(item)
        bar=row();self.hint=label('','muted');bar.addWidget(self.hint,1)
        if version_id and not flat:bar.addWidget(button('全部跟随全局',self.inherit_all))
        outer.addLayout(bar)
        if flat:
            def enable_controls(checked):
                self.stack.setEnabled(checked)
                for field in list(self.fields.values())+self.custom_controls:field.setEnabled(checked)
                memory_state()
                name=window.instances.display_name(self.vid)
                self.scope_description.setText(
                    f'以下修改仅对“{name}”生效，不会修改全局设置或其他实例。'
                    if checked else '当前实例跟随全局设置。下方仅展示全局值；请前往“设置 → 全局游戏设置”修改。开启独立设置仅影响当前实例。')
                self.global_settings_button.setVisible(not checked)
            def specific_changed(checked):
                enable_controls(checked);self.mark_dirty()
            self.specific.toggled.connect(specific_changed)
            enable_controls(self.specific.isChecked())

        if not version_id:
            for key in APPEARANCE_KEYS:
                preview_field=self.fields.get(key)
                if isinstance(preview_field,QCheckBox):preview_field.toggled.connect(self.queue_preview)
                elif isinstance(preview_field,QSpinBox):preview_field.valueChanged.connect(self.queue_preview)
                elif isinstance(preview_field,QComboBox):preview_field.currentIndexChanged.connect(self.queue_preview)
                elif isinstance(preview_field,QLineEdit):preview_field.textChanged.connect(self.queue_preview)
        self.ready=True;self.dirty=False
        if not version_id:self.refresh_color_feedback()

    def _autosave(self):
        if not self.dirty:return
        self.save(quiet=True)

    def flush(self):
        for field in self.fields.values():
            if isinstance(field,QSpinBox) and field.isEnabled():field.interpretText()
        self.autosave_timer.stop()
        return not self.dirty or self.save(quiet=True)

    def open_global_settings(self):
        self.launcher.navigate('settings')
        self.launcher.open_settings_tab(self.launcher.settings_editor.tab_names['全局游戏设置'])

    def select_tab(self,index):
        self.stack.setCurrentIndex(index)
        for i,item in enumerate(self.tabs):item.setChecked(i==index)

    def mark_dirty(self,*args):
        if not self.ready:return
        self.dirty=True
        self.autosave_timer.start()

    def initial(self,key):
        if key in self.values:return self.values[key]
        translated={'width':'window_width','height':'window_height','isolate':'version_isolation'}
        return self.launcher.config_obj.get(translated.get(key,key))

    def add(self,card,key,title,description,field,control=None):
        field.setObjectName('setting_'+key);self.fields[key]=field
        if self.vid and not self.flat:
            if control is None:field.setMinimumWidth(360 if field.property('wideEditor') else 220);field.setMaximumWidth(960 if field.property('wideEditor') else 310)
            holder=column(spacing=5);holder.addWidget(control if control is not None else field)
            override=QCheckBox('单独设置');override.setChecked(key in self.values);self.overrides[key]=override
            field.setEnabled(override.isChecked());override.toggled.connect(field.setEnabled);override.toggled.connect(self.mark_dirty);holder.addWidget(override)
            if control is not None:control.setEnabled(override.isChecked());override.toggled.connect(control.setEnabled)
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
        else:setting_row(card.body,title,description,control if control is not None else field)
        if isinstance(field,QCheckBox):field.toggled.connect(self.mark_dirty)
        elif isinstance(field,QSpinBox):field.valueChanged.connect(self.mark_dirty)
        elif isinstance(field,QComboBox):field.currentIndexChanged.connect(self.mark_dirty)
        else:field.textChanged.connect(self.mark_dirty)

    def edit(self,card,key,title,description,placeholder,browse=None):
        field=QLineEdit(str(self.initial(key) or ''));field.setPlaceholderText(placeholder)
        if browse or key in ('jvm_args','game_args','server_address','home_welcome_large','home_welcome_small'):field.setProperty('wideEditor',True)
        self.add(card,key,title,description,field)
        if browse:
            def choose():
                path=(QFileDialog.getExistingDirectory(self,'选择游戏库',field.text()) if browse=='directory' else QFileDialog.getOpenFileName(self,'选择 Java',field.text(),'Java (java.exe javaw.exe);;所有文件 (*)')[0])
                if path:
                    if key in self.overrides:self.overrides[key].setChecked(True)
                    field.setText(path)
            action=field.addAction(icon('folder',paint_color(self,'icon')),QLineEdit.ActionPosition.TrailingPosition);action.setProperty('onionGlyph','folder');action.setToolTip('浏览目录' if browse=='directory' else '浏览 Java');action.triggered.connect(choose)

    def spin(self,card,key,title,description,low,high,step):
        field=InlineSpinBox();field.setRange(low,high);field.setSingleStep(step);field.setKeyboardTracking(False);field.setValue(int(self.initial(key) or 0))
        unit='MiB' if key in ('min_memory','max_memory') else 'px' if key in ('width','height','window_width','window_height') else 'KiB/s' if key=='download_speed_limit' else ''
        holder=self.number_holder(key,field,unit) if unit else None
        self.add(card,key,title,description,field,holder)

    def number_holder(self,key,field,unit,slider=None):
        holder=QWidget();holder.setObjectName('numberEditor');holder.setMinimumWidth(320);holder.setMaximumWidth(420)
        line=row(holder,0,8)
        if slider is not None:line.addWidget(slider,1)
        else:line.addStretch(1)
        if key=='download_speed_limit':
            hint=label('','muted');hint.setFixedWidth(60);self.number_hints[key]=hint;line.addWidget(hint)
            def update_hint(value):hint.setText('不限速' if value==0 else '')
            field.valueChanged.connect(update_hint);update_hint(field.value())
        field.setSuffix('');field.setSpecialValueText('');field.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        field.setAlignment(Qt.AlignmentFlag.AlignRight);field.setFixedWidth(96);line.addWidget(field)
        caption=label(unit,'muted');caption.setFixedWidth(48);caption.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(caption);self.unit_labels[key]=caption;self.numeric_holders[key]=holder
        return holder

    def percentage(self,card,key,title,description,high):
        self.number_slider(card,key,title,description,0,high,'%',preview=True)

    def number_slider(self,card,key,title,description,low,high,suffix='',preview=False):
        field=InlineSpinBox();field.setRange(low,high);field.setSingleStep(1);field.setKeyboardTracking(False)
        field.setValue(int(self.initial(key) or 0));field.setAccessibleName(title+'数值')
        slider=SettingsSlider(Qt.Orientation.Horizontal);slider.setRange(low,high);slider.setSingleStep(1);slider.setPageStep(5)
        slider.setMinimumHeight(28);slider.setValue(field.value());slider.setAccessibleName(title+'滑动条')
        slider.valueChanged.connect(field.setValue);field.valueChanged.connect(slider.setValue)
        holder=self.number_holder(key,field,suffix.strip(),slider);self.sliders[key]=slider
        self.add(card,key,title,description,field,holder)
        if preview:field.valueChanged.connect(self.queue_preview)

    def queue_preview(self,*args):
        if self.ready and not self.preview_timer.isActive():self.preview_timer.start()

    def preview_transparency(self):
        if self.vid:return
        self.launcher.config_obj._qt_appearance_preview={
            key:(field.isChecked() if isinstance(field,QCheckBox) else field.value() if isinstance(field,QSpinBox)
                 else field.currentData() if isinstance(field,QComboBox) else field.text().strip())
            for key,field in self.fields.items() if key in APPEARANCE_KEYS}
        self.launcher.apply_appearance()
        self.refresh_color_feedback()

    def refresh_color_feedback(self,*args):
        if self.vid or not hasattr(self,'palette_feedback'):return
        automatic=self.fields['accent_source'].currentData()=='wallpaper'
        self.fields['accent_color'].setEnabled(not automatic)
        self.choose_accent_button.setText('改用自定义颜色' if automatic else '选择颜色')
        config=self.launcher.config_obj;accent=effective_accent(config)
        if automatic:
            if getattr(config,'_qt_wallpaper_seed_found',False):
                text='壁纸取色 '+config._qt_wallpaper_seed+' → '+accent
            else:text='壁纸无可用取色，使用默认紫色 → '+accent
        else:text='自定义 → '+accent
        self.palette_feedback.setText(text)

    def reset_appearance(self):
        from ..config import DEFAULTS
        for key in APPEARANCE_KEYS:
            field=self.fields.get(key)
            if field is None:continue
            value=DEFAULTS[key]
            if isinstance(field,QCheckBox):field.setChecked(value)
            elif isinstance(field,QSpinBox):field.setValue(value)
            elif isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            else:field.setText(value)
        self.mark_dirty();self.queue_preview()

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

    def save(self,quiet=False):
        self.autosave_timer.stop()
        self.preview_timer.stop()
        w=self.launcher
        try:
            if w.mutating or w.launch_pending:
                self.hint.setText('当前任务结束后自动保存')
                if self.dirty:self.autosave_timer.start(700)
                return False
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
                metadata={key:values.pop(key) for key in ('name','group','notes') if key in values}
                if self.flat and not self.specific.isChecked():values={}
                self.version_store.set(self.vid,values)
                if metadata:self.meta_store.update(self.vid,**metadata)
            else:
                previous={key:w.config_obj.get(key) for key in values}
                changed={key for key,value in values.items() if previous[key]!=value}
                if 'game_dir' in changed:
                    w.game_libraries.remember(w.selected_version)
                    values['selected_version']=w.game_libraries.selection(values['game_dir'])
                w.config_obj.update(values)
                w.config_obj._qt_appearance_preview={}
                if changed & APPEARANCE_KEYS:
                    w.apply_appearance();self.refresh_color_feedback()
                from .motion import apply_motion_preferences
                apply_motion_preferences(w)
                if 'game_dir' in changed:w.activate_game_library()
                elif changed & {'download_source','proxy_host','proxy_port','max_download_threads','download_speed_limit'}:
                    from ..repository import GameRepository
                    w.repo=GameRepository(w.config_obj)
                if w.instance_editor:w.instance_editor.refresh_inherited()
            self.dirty=False;self.refresh_inherited();self.hint.setText('');w.status.setText('')
            if self.vid and metadata:w.reload_versions(refresh_page=False)
            return True
        except Exception as error:
            self.hint.setText('未保存：'+str(error));w.status.setText('设置未保存：'+str(error))
            if not quiet:w.error(error)
            return False


class InstanceSettingsDialog(QDialog):
    def __init__(self,window,vid):
        super().__init__(window);self.setWindowTitle('实例设置 · '+window.instances.display_name(vid));self.resize(1020,760);self.setMinimumSize(850,620)
        body=column(self,24,18);body.addWidget(label(window.instances.display_name(vid),'title'))
        body.addWidget(label('实例设置  /  未单独设置的项目将跟随全局配置','muted'))
        self.editor=SettingsEditor(window,vid);body.addWidget(self.editor,1)

    def reject(self):
        self.editor.flush()
        if self.editor.dirty and QMessageBox.question(self,'尚未保存','放弃未保存的实例设置？')!=QMessageBox.StandardButton.Yes:return
        super().reject()
