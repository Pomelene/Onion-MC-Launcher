"""Onion Minecraft Launcher Qt shell: HMCL-inspired navigation and native high-DPI rendering."""
import sys
import time
from pathlib import Path
from .choices import ActionMenu
from PySide6.QtCore import Qt,Signal,Slot,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QStackedWidget,QComboBox,
    QLineEdit,QPlainTextEdit,QMessageBox,QInputDialog,QDialog,QFormLayout,QCheckBox,QSpinBox,QProgressBar,QSizePolicy)
from .widgets import STYLE,themed_style,Page,Card,Empty,label,button,column,row,clear,icon,TaskDialog,NavigationItem,GlassBackdrop,configure_fonts
from .motion import NavigationSurface
from .widgets import FeedbackLabel
from .chrome import ChromeMainWindow,TitleBar,window_controls,install_window_chrome
from .tasks import TaskManager
from .actions import Actions
from .pages import Pages
from .library_actions import LibraryActions
from ..paths import app_root,default_settings_path,default_accounts_path,LAUNCHER_VERSION,LAUNCHER_NAME
from ..config import Config
from ..accounts import AccountStore
from ..repository import GameRepository
from ..instance import InstanceStore
from ..version_settings import VersionSettingsStore


class MainWindow(ChromeMainWindow,Actions,Pages,LibraryActions):
    game_log=Signal(str,bool)
    game_exit=Signal(int)

    def __init__(self,config_path=None,root=None):
        super().__init__();install_window_chrome(QApplication.instance());self.root=Path(root or app_root());self.config_obj=Config(config_path or self.root/'onionmcl.json')
        from ..storage import is_portable
        portable=self.config_obj.path if is_portable(self.config_obj.path) else None
        self.repo=GameRepository(self.config_obj);self.accounts=AccountStore(portable or self.root/'config/accounts.json')
        from ..game_libraries import GameLibraries
        self.game_libraries=GameLibraries(self.config_obj);self.game_libraries.ensure_current();self.bind_game_library()
        self.tasks=TaskManager(self)
        from ..task_history import TaskHistory
        self.task_history=TaskHistory(self.root)
        self.versions=[];self.kinds={};self.selected_version=self.config_obj.get('selected_version') or ''
        self.page_seq={};self.process=None;self.launch_pending=False;self.started_at=0;self.mutating=False;self.dialogs=[]
        self.setWindowTitle(f'{LAUNCHER_NAME} {LAUNCHER_VERSION}')
        resource=Path(getattr(sys,'_MEIPASS',self.root))/'assets/craftbridge.ico'
        if resource.exists():self.setWindowIcon(QIcon(str(resource)))
        self.setStyleSheet(themed_style(self.config_obj.get('accent_color'),self.config_obj));self._build();self.apply_appearance();self.game_log.connect(self.append_log);self.game_exit.connect(self.exited)
        from .window_size import restore_window_size
        restore_window_size(self,self.config_obj)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._system_mode_changed)
        self.refresh_account();self.navigate('home');QTimer.singleShot(0,self.reload_versions)

    def _build(self):
        shell=GlassBackdrop();outer=column(shell,0,0);self.setCentralWidget(shell)
        toolbar=TitleBar(self.frame_controller);toolbar.setFixedHeight(64);self.title_bar=toolbar;top=row(toolbar,0,0)
        toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        home_area=QWidget();home_area.setFixedWidth(220);home_line=row(home_area,12,0)
        self.home_area=home_area;self.home_line=home_line
        self.home_button=button('返回首页',lambda:self.navigate('home'),'soft','home');self.home_button.setAccessibleName('返回首页');home_line.addWidget(self.home_button);home_line.addStretch();top.addWidget(home_area)
        heading=QWidget();heading_line=row(heading,0,10);heading_line.setContentsMargins(24,0,12,0);top.addWidget(heading,1)
        self.heading_area=heading;self.heading_line=heading_line
        self.back_button=button('',self.go_back,glyph='back');self.back_button.setFixedSize(30,34);self.back_button.setStyleSheet('padding:0;');self.back_button.setToolTip('返回上一页');self.back_button.setAccessibleName('返回上一页');heading_line.addWidget(self.back_button)
        self.title=label('','heading');self.title.setMinimumWidth(0);self.title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);heading_line.addWidget(self.title,1)
        self.brand_widget=QWidget();branding=row(self.brand_widget,0,8);branding.addWidget(label('Onion','heading'));branding.addWidget(label(LAUNCHER_VERSION,'pill'),0,Qt.AlignmentFlag.AlignVCenter);heading_line.addWidget(self.brand_widget);top.addWidget(window_controls(self.frame_controller));outer.addWidget(toolbar)
        lower=row(spacing=0);outer.addLayout(lower,1)
        side=NavigationSurface();side.setObjectName('sidebar');side.setFixedWidth(220)
        self.sidebar=side
        self.sidebar_body=column(side,0,0);self.sidebar_body.setSizeConstraint(self.sidebar_body.SizeConstraint.SetDefaultConstraint);self.nav={};self.account_button=None
        self.nav_motion=side.selection;self.sidebar_scheme=None
        lower.addWidget(side)
        main=QWidget();main.setObjectName('workspace');body=column(main,0,0);lower.addWidget(main,1)
        self.stack=QStackedWidget();self.page_map={};body.addWidget(self.stack,1)
        for key in ('home','instance','versions','download','settings','about','tools'):
            page=Page() if key not in ('home','instance','download','tools') else QWidget()
            if isinstance(page,Page):page.body.setContentsMargins(24,20,24,20)
            else:page.body=column(page,0,0)
            self.page_map[key]=page;self.stack.addWidget(page)
        self.status=FeedbackLabel();self.status.setContentsMargins(14,4,14,4);body.addWidget(self.status)
        self.task_strip=QWidget();strip=column(self.task_strip,10,5);info=row(spacing=8)
        self.task_stage=label('','muted');info.addWidget(self.task_stage,1);self.task_amount=label('','muted');info.addWidget(self.task_amount)
        self.task_cancel=button('取消',self.cancel_active_task);info.addWidget(button('任务中心',lambda:self.open_task_center(),'soft','history'));info.addWidget(self.task_cancel);strip.addLayout(info)
        self.task_progress=QProgressBar();self.task_progress.setTextVisible(False);strip.addWidget(self.task_progress);body.addWidget(self.task_strip);self.task_strip.hide();self.active_task=None
        self.selector=QComboBox(self);self.selector.hide();self.selector.currentIndexChanged.connect(self.choose_version)
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(3000)
        self.instance_tab='game';self.instance_context='';self.instance_editor=None;self.settings_editor=None;self.subpages=[];self.nav_history=[];self.current_route=None

    def show_subpage(self,view):
        view.embedded=True;view.setProperty('embedded',True);view.setModal(False);view.setParent(self.stack,Qt.WindowType.Widget)
        view.setMinimumSize(0,0);self.stack.addWidget(view);self.subpages.append(view)
        view.finished.connect(lambda _:self.finish_subpage(view))
        self.stack.setCurrentWidget(view);view.show();self.title.setText(getattr(view,'navigation_title',view.windowTitle()));self.back_button.show()
        self.sync_header_layout()

    def finish_subpage(self,view):
        if view not in self.subpages:return
        self.subpages.remove(view);self.stack.removeWidget(view);view.hide()
        if self.subpages:
            target=self.subpages[-1];self.stack.setCurrentWidget(target);self.title.setText(getattr(target,'navigation_title',target.windowTitle()))
        else:
            self.stack.setCurrentWidget(self.page_map[self.current_page]);self.title.setText(getattr(self,'page_title','Onion'));self.back_button.setVisible(self.current_page!='home')
        self.sync_header_layout()

    def sync_header_layout(self):
        home=getattr(self,'current_page',None)=='home' and not self.subpages
        parent=self.home_area if home else self.heading_area
        if self.brand_widget.parentWidget() is not parent:
            self.home_line.removeWidget(self.brand_widget);self.heading_line.removeWidget(self.brand_widget)
            self.brand_widget.setParent(parent)
            if home:self.home_line.insertWidget(0,self.brand_widget)
            else:self.heading_line.addWidget(self.brand_widget)
            self.brand_widget.show()
        self.home_button.setVisible(not home)

    def go_back(self):
        if self.subpages:
            view=self.subpages[-1]
            if isinstance(view,TaskDialog):self.finish_subpage(view)
            else:view.reject()
        elif self.nav_history:
            key,instance_tab,download_kind=self.nav_history.pop()
            if instance_tab:self.instance_tab=instance_tab
            if download_kind:self.download_kind=download_kind
            self.navigate(key,record_history=False)
        else:self.navigate('home',record_history=False)


    def build_sidebar(self,key):
        scheme=key if key in ('settings','download','tools','versions') or (key=='instance' and self.selected_version) else 'main'
        same_scheme=scheme==self.sidebar_scheme
        if same_scheme and scheme!='versions':
            self.refresh_account();self.update_selection();self.update_sidebar_selection(key);return
        self.nav_motion.select(None,False)
        self.sidebar_scheme=scheme
        clear(self.sidebar_body);nav=self.sidebar_body;self.nav={};self.account_button=None
        def heading(text):
            item=label(text,'eyebrow');item.setContentsMargins(16,18,16,8);nav.addWidget(item);item.show()
        def entry(name,title,glyph,callback,subtitle=''):
            item=NavigationItem(title,glyph,callback,subtitle);nav.addWidget(item);item.show();self.nav[name]=item;return item
        if key=='versions':
            from .game_libraries import LibraryRail
            self.library_rail=LibraryRail(self);nav.addWidget(self.library_rail,1)
        elif key=='instance' and self.selected_version:
            for name,title,glyph in [('game','游戏设置','settings'),('auto','自动安装','package'),('mods','模组管理','package'),('resourcepacks','资源包管理','grid'),('shaderpacks','光影管理','world'),('worlds','世界管理','world'),('schematics','原理图管理','schematic'),('screenshots','截图管理','image'),('logs','运行日志','history')]:
                item=entry(name,title,glyph,lambda k=name:self.open_instance_tab(k));item.setChecked(name==self.instance_tab)
            nav.addStretch();entry('launch','启动游戏','play',self.launch_selected);entry('folder','浏览实例目录','folder',lambda:self.open_folder(self.repo.run_dir(self.selected_version)));entry('info','管理','settings',lambda:self.open_instance_tab('info'))
        elif key=='tools':
            for name,title,glyph in [('skins','皮肤管理','skin'),('seedmap','种子地图','world'),('tasks','任务中心','history')]:
                item=entry(name,title,glyph,lambda k=name:self.open_tools_tab(k));item.setChecked(name==getattr(self,'tools_tab','skins'))
            nav.addStretch()
        elif key=='settings' and self.settings_editor:
            for title,index in self.settings_editor.tab_names.items():
                item=entry(title,title,'java' if title=='Java 管理' else 'settings',lambda i=index:self.open_settings_tab(i));item.setChecked(index==self.settings_editor.stack.currentIndex())
            nav.addStretch();entry('about','关于','package',lambda:self.navigate('about'))
        elif key=='download':
            heading('新游戏');entry('install','安装游戏','grid',self.install_dialog)
            item=entry('modpack','整合包','package',lambda:self.choose_download_kind('modpack'));item.setChecked(getattr(self,'download_kind','mod')=='modpack')
            heading('游戏内容')
            for name,title,glyph in [('mod','模组','package'),('resourcepack','资源包','grid'),('shader','光影','world')]:
                item=entry(name,title,glyph,lambda k=name:self.choose_download_kind(k));item.setChecked(name==getattr(self,'download_kind','mod'))
            nav.addStretch();entry('import','导入整合包','plus',self.import_modpack)
        else:
            heading('账户');account=self.accounts.current()
            self.account_button=entry('account',account.username if account else '添加账户','account',self.open_accounts)
            self.account_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.account_button.customContextMenuRequested.connect(self.show_account_menu)
            heading('游戏');entry('instance','实例管理','settings',lambda:self.navigate('instance'),self.instances.display_name(self.selected_version) if self.selected_version else '尚未选择游戏实例')
            entry('versions','实例列表','grid',lambda:self.navigate('versions'));entry('download','下载','download',lambda:self.navigate('download'))
            heading('通用');entry('tools','工具坊','tools',lambda:self.navigate('tools'));entry('settings','设置','settings',lambda:self.navigate('settings'));entry('about','关于','package',lambda:self.navigate('about'));nav.addStretch()
            for name,item in self.nav.items():item.setChecked(name==key)
        self.update_selection()
        self.sync_navigation_motion(False)

    def update_sidebar_selection(self,key):
        for name,item in self.nav.items():
            if self.sidebar_scheme=='instance':selected=name==self.instance_tab
            elif self.sidebar_scheme=='settings':selected=name in self.settings_editor.tab_names and self.settings_editor.tab_names[name]==self.settings_editor.stack.currentIndex()
            elif self.sidebar_scheme=='download':selected=name==getattr(self,'download_kind','mod')
            elif self.sidebar_scheme=='tools':selected=name==getattr(self,'tools_tab','skins')
            else:selected=name==key
            item.setChecked(selected)
        self.sync_navigation_motion()

    def sync_navigation_motion(self,animate=True):
        self.nav_motion.select(next((item for item in self.nav.values() if item.isChecked()),None),animate)

    def open_instance_tab(self,key):
        route=('instance',key,None)
        if self.current_route==route:return
        if self.current_route and self.current_route!=route:self.nav_history.append(self.current_route)
        self.current_route=route
        self.instance_tab=key;self.instance_workspace.open_tab(key)
        for name,item in self.nav.items():item.setChecked(name==key)
        self.sync_navigation_motion()

    def open_settings_tab(self,index):
        if self.settings_editor.stack.currentIndex()==index:return
        self.settings_editor.select_tab(index)
        for name,item in self.nav.items():item.setChecked(name in self.settings_editor.tab_names and self.settings_editor.tab_names[name]==index)
        self.sync_navigation_motion()

    def choose_download_kind(self,kind):
        self.download_kind=kind;self.navigate('download')

    def open_tools_tab(self,key):
        self.tools_tab=key;self.workshop.open_tab(key);self.update_sidebar_selection('tools')

    def build_tools(self):
        if not hasattr(self,'workshop'):
            from .workshop import Workshop
            self.workshop=Workshop(self);self.page_map['tools'].body.addWidget(self.workshop)
        self.workshop.open_tab(getattr(self,'tools_tab','skins'))

    def open_task_center(self):
        active=self.active_task
        if active:active.background()
        self.navigate('tools');self.open_tools_tab('tasks')
        if active:
            key=next((key for key,value in self.task_history.live.items() if value is active),None)
            if key:self.workshop.views['tasks'].select_task(key)

    def navigate(self,key,record_history=True,force=False):
        self.flush_settings()
        for view in list(reversed(self.subpages)):
            if not isinstance(view,TaskDialog):view.reject()
            self.finish_subpage(view)
        if key in ('mods','worlds','logs','resourcepacks','shaderpacks','schematics','screenshots'):
            self.instance_tab=key;key='instance'
        route=(key,self.instance_tab if key=='instance' else None,getattr(self,'download_kind','mod') if key=='download' else None)
        if route==self.current_route and not force:
            self.update_selection();self.build_sidebar(key);return
        if record_history and self.current_route and route!=self.current_route:
            self.nav_history.append(self.current_route);self.nav_history=self.nav_history[-40:]
        self.current_route=route
        self.current_page=key;self.back_button.setVisible(key!='home');self.stack.setCurrentWidget(self.page_map[key])
        self.sync_header_layout()
        titles={'home':'','instance':'实例管理 · '+self.instances.display_name(self.selected_version),'versions':'实例列表','download':'下载','settings':'设置','about':'关于 Onion','tools':'工具坊'}
        self.page_title=titles[key];self.title.setText(titles[key])
        if key=='instance':self.build_instance()
        elif key!='settings' or self.settings_editor is None:getattr(self,'build_'+key)()
        self.build_sidebar(key)
        if key=='download':
            from .browser import TITLES
            self.page_title='下载 / '+TITLES[getattr(self,'download_kind','mod')];self.title.setText(self.page_title)

    def page(self,key):
        if key=='logs':self.logs.setParent(None)
        self.page_seq[key]=self.page_seq.get(key,0)+1
        if key in ('mods','worlds','logs'):
            page=self.instance_content
        else:page=self.page_map[key]
        clear(page.body);return page.body

    def update_selection(self):
        vid=self.selected_version
        if 'instance' in self.nav:
            self.nav['instance'].setSubtitle(self.instances.display_name(vid) if vid else '尚未选择游戏实例')
            self.nav['instance'].setEnabled(bool(vid))
        if hasattr(self,'launch_button'):
            self.launch_button.setText(('启动游戏\n'+self.instances.display_name(vid)) if vid else '安装游戏\n选择 Minecraft 版本')
            self.quick_button.setEnabled(bool(self.versions))

    def show_account_menu(self,point):
        from PySide6.QtWidgets import QMenu
        menu=ActionMenu(self)
        for record in self.accounts.accounts:
            action=menu.addAction(record.label);action.setCheckable(True);action.setChecked(record.uuid==self.accounts.current_uuid)
            action.triggered.connect(lambda checked=False,uid=record.uuid:self.switch_account(uid))
        menu.addSeparator();menu.addAction('管理账户',self.open_accounts);menu.exec(self.account_button.mapToGlobal(point))

    def switch_account(self,uid):
        self.accounts.set_current(uid);self.refresh_account()

    def quick_select(self):
        from .workspace import InstancePicker
        picker=InstancePicker(self);self.dialogs.append(picker);picker.show_above(self.quick_button)

    def reload_versions(self,refresh_page=True):
        repo=self.repo
        def scan(job):
            versions=repo.list_installed();return versions,{v:repo.loader_label(v) for v in versions}
        def done(result):
            if repo is not self.repo:return
            self.versions,self.kinds=result
            overview=getattr(self,'_overview_target',None)
            if overview:
                from ..storage import directory_key
                if overview[0]==directory_key(repo.game_dir):
                    self._overview_target=None
                    if overview[1] in self.versions:self.selected_version=overview[1]
                    else:self.status.setText('目标实例已不在该目录中，请刷新实例总览');overview=None
            if self.selected_version not in self.versions:self.selected_version=self.versions[0] if self.versions else ''
            self.selector.blockSignals(True);self.selector.clear()
            for vid in self.versions:self.selector.addItem(self.instances.display_name(vid),vid)
            if not self.versions:self.selector.addItem('尚未安装游戏','')
            self.selector.setCurrentIndex(max(0,self.selector.findData(self.selected_version)));self.selector.blockSignals(False)
            self.update_selection()
            self.game_libraries.remember(self.selected_version)
            if refresh_page and self.current_page!='settings':self.navigate(self.current_page,force=True)
            if overview:self.navigate(overview[2],force=True)
        self.tasks.submit(scan,done,self.error)

    def choose_version(self,index):
        vid=self.selector.itemData(index)
        if vid:self.set_selected(vid)

    def set_selected(self,vid,refresh_page=True):
        if vid not in self.versions:return False
        if vid!=self.selected_version and not self.flush_settings():return False
        self.selected_version=vid;self.game_libraries.remember(vid)
        self.selector.blockSignals(True);self.selector.setCurrentIndex(self.selector.findData(vid));self.selector.blockSignals(False)
        self.update_selection()
        if self.current_page=='instance':self.build_instance()
        elif self.current_page=='versions' and refresh_page:self.build_versions()
        return True

    def flush_settings(self):
        results=[editor.flush() for editor in (self.settings_editor,self.instance_editor) if editor]
        return all(results)

    def _system_mode_changed(self,*args):
        from .theme import preference
        if preference(self.config_obj,'color_mode','dark')=='auto':self.apply_appearance()

    def apply_appearance(self):
        from .theme import paint_color,preference,APPEARANCE_KEYS,resolved_mode
        from .color_science import wallpaper_seed_info
        from .widgets import HomeCanvas,ContentRow
        from PySide6.QtGui import QFont,QFontDatabase
        self.config_obj._qt_wallpaper_seed,self.config_obj._qt_wallpaper_seed_found=wallpaper_seed_info(preference(self.config_obj,'background_image','')) if preference(self.config_obj,'accent_source','custom')=='wallpaper' else ('#cebafa',False)
        current={key:preference(self.config_obj,key) for key in APPEARANCE_KEYS|{'ui_animations'}}
        current['_resolved_mode']=resolved_mode(self.config_obj)
        current['_wallpaper_seed']=self.config_obj._qt_wallpaper_seed
        try:current['_wallpaper_stamp']=Path(current['background_image']).stat().st_mtime_ns if current.get('background_image') else 0
        except OSError:current['_wallpaper_stamp']=0
        previous=getattr(self,'_appearance_snapshot',{})
        changed={key for key,value in current.items() if previous.get(key)!=value}
        if previous and not changed:return
        if not previous or changed & {'font_family','font_size','log_font_family','log_font_size','font_antialiasing'}:
            family=preference(self.config_obj,'font_family','') or 'Microsoft YaHei UI'
            if family not in QFontDatabase.families():family='Microsoft YaHei UI'
            font=QFont(family);font.setPixelSize(int(preference(self.config_obj,'font_size',14)))
            strategy=QFont.StyleStrategy.PreferAntialias
            if preference(self.config_obj,'font_antialiasing','auto')=='gray':strategy|=QFont.StyleStrategy.NoSubpixelAntialias
            font.setStyleStrategy(strategy);self.setFont(font)
            log_family=preference(self.config_obj,'log_font_family','Consolas') or family
            if log_family not in QFontDatabase.families():log_family='Consolas'
            self.logs.setStyleSheet("font-family:'"+log_family.replace("'",'')+"';font-size:"+str(preference(self.config_obj,'log_font_size',12))+"px;")
        if not previous or changed & {'font_size'}:
            for item in self.findChildren(ContentRow):item.apply_appearance()
            for item in self.findChildren(NavigationItem):item.setSubtitle(item.subtitle)
        if not previous or changed & {'animation_duration','ui_animations'}:
            from .motion import apply_motion_preferences
            apply_motion_preferences(self)
        style=themed_style(self.config_obj.get('accent_color'),self.config_obj)
        if self.styleSheet()!=style:self.setStyleSheet(style)
        shared=preference(self.config_obj,'background_scope')=='window'
        for surface in (self.sidebar,self.title_bar):
            if surface.property('wallpaperUnderlay')!=shared:
                surface.setProperty('wallpaperUnderlay',shared)
                surface.style().unpolish(surface);surface.style().polish(surface);surface.update()
        for canvas in self.findChildren(HomeCanvas):
            canvas.set_background(preference(self.config_obj,'background_image'));canvas.update()
        if not previous or changed & {'accent_color','accent_source','color_style','color_mode','_resolved_mode','_wallpaper_seed'}:
            for field in self.findChildren(QLineEdit):
                for action in field.actions():
                    if action.property('onionGlyph'):action.setIcon(icon(action.property('onionGlyph'),paint_color(field,'icon')))
        for dialog in self.findChildren(QDialog):
            if getattr(dialog,'_chrome_header',None):
                if dialog.styleSheet()!=style:dialog.setStyleSheet(style)
        self._appearance_snapshot=current
        self.centralWidget().update()

    def refresh_account(self):
        account=self.accounts.current()
        if self.account_button:
            self.account_button.setText(account.username if account else '添加账户')
            self.account_button.setSubtitle('')

    def open_accounts(self):
        from .accounts import AccountsDialog
        dialog=AccountsDialog(self);self.dialogs.append(dialog);self.show_subpage(dialog)

    def open_folder(self,path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def error(self,error):
        self.status.setText(str(error));QMessageBox.warning(self,'操作未完成',str(error))

    def task(self,title,work,done=None,mutates=True,retry=None,task_repo=None,task_instance=None):
        if mutates and self.mutating:self.error('已有文件操作进行中，请等待完成或取消当前任务。');return
        if mutates:self.mutating=True
        dialog=TaskDialog(self,title);self.dialogs.append(dialog)
        task_repo=task_repo or self.repo
        record=self.task_history.begin(title,task_repo.game_dir,self.selected_version if task_instance is None else task_instance)
        if retry:self.task_history.retries[record['id']]=retry
        self.active_task=dialog;self.task_strip.show();self.task_cancel.setEnabled(True);self.task_stage.setText(title+' · 准备中…');self.task_amount.setText('');self.task_progress.setRange(0,0)
        def progress(value):
            self.task_history.progress(record,value)
            dialog.update_progress(value)
            if self.active_task is not dialog:return
            if isinstance(value,str):
                self.task_stage.setText(title+' · '+value);self.task_amount.setText('');self.task_progress.setRange(0,0)
            elif isinstance(value,tuple) and len(value)==2:
                completed,total=value
                if total>0:
                    self.task_progress.setRange(0,1000);self.task_progress.setValue(min(1000,int(completed*1000/total)))
                    self.task_amount.setText(f'{completed:,} / {total:,}  ·  {min(100,int(completed*100/total))}%')
                else:self.task_progress.setRange(0,0);self.task_amount.setText('正在处理…')
        def finish():
            if self.active_task is dialog:self.active_task=None;self.task_strip.hide()
        def success(value):
            if mutates:self.mutating=False
            self.task_history.finish(record,'cancelled' if dialog.job.cancel.is_set() else 'complete')
            dialog.complete();dialog.accept();finish();self.status.setText('任务已取消' if dialog.job.cancel.is_set() else title+' · 完成')
            if done:done(value)
        def failure(error):
            if mutates:self.mutating=False
            self.task_history.finish(record,'cancelled' if dialog.job and dialog.job.cancel.is_set() else 'failed',str(error))
            dialog.complete(failed=True);dialog.accept();finish()
            if dialog.job and dialog.job.cancel.is_set():self.status.setText('任务已取消')
            else:self.error(error)
        dialog.job=self.tasks.submit(work,success,failure,progress,task_repo.downloader)
        self.task_history.live[record['id']]=dialog
        dialog.open();return dialog.job

    def cancel_active_task(self):
        if self.active_task:
            self.active_task.cancel_job();self.task_cancel.setEnabled(False);self.task_stage.setText('正在取消，请稍候…')

    @Slot(str,bool)
    def append_log(self,text,is_error=False):
        self.logs.appendPlainText(text)

    @Slot(int)
    def exited(self,code):
        self.stop_offline_skin()
        self.launch_pending=False
        if self.started_at:
            store=getattr(self,'running_instance_store',self.instances);store.load()
            store.add_play_time(self.running_version,time.time()-self.started_at)
            if store is not self.instances:self.instances.load()
        self.started_at=0;self.status.setText(f'游戏已退出 · 代码 {code}')
        if self.config_obj.get('keep_launcher_open'):self.show();self.raise_()
        else:self.close()

    def closeEvent(self,event):
        if self.tasks.jobs:
            if QMessageBox.question(self,'后台任务仍在运行','取消后台任务并在结束后关闭启动器？')!=QMessageBox.StandardButton.Yes:event.ignore();return
            self.tasks.cancel_all();self.hide();event.ignore()
            self.close_timer=QTimer(self);self.close_timer.timeout.connect(lambda:self.close() if not self.tasks.jobs else None);self.close_timer.start(200)
            return
        self.flush_settings()
        editors=[self.settings_editor,self.instance_editor]
        if any(editor and editor.dirty for editor in editors):
            if QMessageBox.question(self,'尚未保存','关闭并放弃未保存的设置？')!=QMessageBox.StandardButton.Yes:event.ignore();return
            for editor in editors:
                if editor:editor.dirty=False
        from .window_size import remember_window_size
        remember_window_size(self,self.config_obj)
        self.stop_offline_skin();event.accept()

    def stop_offline_skin(self):
        server=getattr(self,'offline_skin_server',None)
        if server:
            self.offline_skin_server=None
            import threading
            threading.Thread(target=server.close,name='OnionSkinShutdown',daemon=True).start()


def main():
    application=QApplication.instance() or QApplication(sys.argv)
    install_window_chrome(application)
    configure_fonts(application)
    application.setApplicationName(LAUNCHER_NAME);application.setStyle('Fusion')
    from ..log import setup_logging
    setup_logging(to_console=False)
    from ..storage import StorageError
    from ..secrets import SecretStorageError
    try:window=MainWindow()
    except (StorageError,SecretStorageError,OSError) as error:
        QMessageBox.critical(None,'启动器数据无法加载',str(error));return 1
    window.show()
    return application.exec()
