"""Onion Minecraft Launcher Qt shell: HMCL-inspired navigation and native high-DPI rendering."""
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt,Signal,Slot,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QStackedWidget,QComboBox,
    QLineEdit,QPlainTextEdit,QMessageBox,QInputDialog,QDialog,QFormLayout,QCheckBox,QSpinBox)
from .widgets import STYLE,Page,Card,Empty,label,button,column,row,clear,icon,TaskDialog,NavigationItem,GlassBackdrop,configure_fonts
from .tasks import TaskManager
from .actions import Actions
from .pages import Pages
from ..paths import app_root,default_settings_path,default_accounts_path,LAUNCHER_VERSION,LAUNCHER_NAME
from ..config import Config
from ..accounts import AccountStore
from ..repository import GameRepository
from ..instance import InstanceStore
from ..version_settings import VersionSettingsStore


class MainWindow(QMainWindow,Actions,Pages):
    game_log=Signal(str,bool)
    game_exit=Signal(int)

    def __init__(self,config_path=None,root=None):
        super().__init__();self.root=Path(root or app_root());self.config_obj=Config(config_path or default_settings_path())
        self.repo=GameRepository(self.config_obj);self.accounts=AccountStore(self.root/'config/accounts.json')
        self.instances=InstanceStore(self.root/'config/instances.json');self.version_settings=VersionSettingsStore(self.root/'config/version_settings.json')
        self.tasks=TaskManager(self);self.versions=[];self.kinds={};self.selected_version=self.config_obj.get('selected_version') or ''
        self.page_seq={};self.process=None;self.launch_pending=False;self.started_at=0;self.mutating=False;self.dialogs=[]
        self.setWindowTitle(f'{LAUNCHER_NAME} {LAUNCHER_VERSION}');self.resize(1440,900);self.setMinimumSize(1100,740)
        resource=Path(getattr(sys,'_MEIPASS',self.root))/'assets/craftbridge.ico'
        if resource.exists():self.setWindowIcon(QIcon(str(resource)))
        self.setStyleSheet(STYLE);self._build();self.game_log.connect(self.append_log);self.game_exit.connect(self.exited)
        self.refresh_account();self.navigate('home');QTimer.singleShot(0,self.reload_versions)

    def _build(self):
        shell=GlassBackdrop();outer=column(shell,0,0);self.setCentralWidget(shell)
        toolbar=QWidget();toolbar.setObjectName('toolbar');top=row(toolbar,10,10)
        self.back_button=button('返回',self.go_back,glyph='back');top.addWidget(self.back_button)
        self.title=label('Onion  '+LAUNCHER_VERSION,'heading');top.addWidget(self.title,1)
        top.addWidget(button('首页',lambda:self.navigate('home'),'soft','home'));outer.addWidget(toolbar)
        lower=row(spacing=0);outer.addLayout(lower,1)
        side=QWidget();side.setObjectName('sidebar');side.setFixedWidth(220)
        self.sidebar_body=column(side,0,0);self.sidebar_body.setSizeConstraint(self.sidebar_body.SizeConstraint.SetDefaultConstraint);self.nav={};self.account_button=None
        lower.addWidget(side)
        main=QWidget();main.setObjectName('workspace');body=column(main,0,0);lower.addWidget(main,1)
        self.stack=QStackedWidget();self.page_map={};body.addWidget(self.stack,1)
        for key in ('home','instance','versions','download','settings','about'):
            page=Page() if key not in ('home','instance') else QWidget()
            if isinstance(page,Page):page.body.setContentsMargins(24,20,24,20)
            else:page.body=column(page,0,0)
            self.page_map[key]=page;self.stack.addWidget(page)
        self.status=label('就绪','muted');self.status.setContentsMargins(14,4,14,4);body.addWidget(self.status)
        self.selector=QComboBox(self);self.selector.hide();self.selector.currentIndexChanged.connect(self.choose_version)
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(3000)
        self.instance_tab='game';self.instance_context='';self.instance_editor=None;self.settings_editor=None;self.subpages=[]

    def show_subpage(self,view):
        view.embedded=True;view.setModal(False);view.setParent(self.stack,Qt.WindowType.Widget)
        view.setMinimumSize(0,0);self.stack.addWidget(view);self.subpages.append(view)
        view.finished.connect(lambda _:self.finish_subpage(view))
        self.stack.setCurrentWidget(view);view.show();self.title.setText(view.windowTitle());self.back_button.show()

    def finish_subpage(self,view):
        if view not in self.subpages:return
        self.subpages.remove(view);self.stack.removeWidget(view);view.hide()
        if self.subpages:
            target=self.subpages[-1];self.stack.setCurrentWidget(target);self.title.setText(target.windowTitle())
        else:
            self.stack.setCurrentWidget(self.page_map[self.current_page]);self.title.setText(getattr(self,'page_title','Onion'));self.back_button.setVisible(self.current_page!='home')

    def go_back(self):
        if self.subpages:self.subpages[-1].reject()
        else:self.navigate('home')


    def build_sidebar(self,key):
        clear(self.sidebar_body);nav=self.sidebar_body;self.nav={};self.account_button=None
        def heading(text):
            item=label(text,'eyebrow');item.setContentsMargins(16,18,16,8);nav.addWidget(item)
        def entry(name,title,glyph,callback,subtitle=''):
            item=NavigationItem(title,glyph,callback,subtitle);nav.addWidget(item);self.nav[name]=item;return item
        if key=='instance' and self.selected_version:
            for name,title,glyph in [('game','游戏设置','settings'),('auto','自动安装','package'),('mods','模组管理','package'),('resourcepacks','资源包管理','grid'),('shaderpacks','光影管理','world'),('worlds','世界管理','world'),('logs','运行日志','history')]:
                item=entry(name,title,glyph,lambda k=name:self.open_instance_tab(k));item.setChecked(name==self.instance_tab)
            nav.addStretch();entry('launch','启动游戏','play',self.launch_selected);entry('folder','浏览实例目录','folder',lambda:self.open_folder(self.repo.run_dir(self.selected_version)));entry('info','管理','settings',lambda:self.open_instance_tab('info'))
        elif key=='settings' and self.settings_editor:
            for title,index in self.settings_editor.tab_names.items():
                item=entry(title,title,'settings',lambda i=index:self.open_settings_tab(i));item.setChecked(index==self.settings_editor.stack.currentIndex())
            entry('java','Java 管理','java',self.manage_java);nav.addStretch();entry('about','关于','package',lambda:self.navigate('about'))
        elif key=='download':
            heading('新游戏');entry('install','游戏','grid',self.install_dialog);entry('modpack','整合包','package',lambda:self.choose_download_kind('modpack'))
            heading('游戏内容')
            for name,title,glyph in [('mod','模组','package'),('resourcepack','资源包','grid'),('shader','光影','world')]:
                item=entry(name,title,glyph,lambda k=name:self.choose_download_kind(k));item.setChecked(name==getattr(self,'download_kind','mod'))
            nav.addStretch();entry('import','导入整合包','plus',self.import_modpack)
        else:
            heading('账户');account=self.accounts.current()
            self.account_button=entry('account',account.username if account else '添加账户','account',self.open_accounts,{'microsoft':'微软账户','authlib':'外置登录','offline':'离线模式'}.get(account.type,'') if account else 'Microsoft / 离线 / 外置')
            self.account_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.account_button.customContextMenuRequested.connect(self.show_account_menu)
            heading('游戏');entry('instance','实例管理','settings',lambda:self.navigate('instance'),self.instances.display_name(self.selected_version) if self.selected_version else '尚未选择游戏实例')
            entry('versions','实例列表','grid',lambda:self.navigate('versions'));entry('download','下载','download',lambda:self.navigate('download'))
            heading('通用');entry('settings','设置','settings',lambda:self.navigate('settings'));entry('about','关于','package',lambda:self.navigate('about'));nav.addStretch()
            for name,item in self.nav.items():item.setChecked(name==key)
        self.update_selection()

    def open_instance_tab(self,key):
        self.instance_tab=key;self.instance_workspace.open_tab(key)
        for name,item in self.nav.items():item.setChecked(name==key)

    def open_settings_tab(self,index):
        self.settings_editor.select_tab(index)
        for name,item in self.nav.items():item.setChecked(name in self.settings_editor.tab_names and self.settings_editor.tab_names[name]==index)

    def choose_download_kind(self,kind):
        self.download_kind=kind;self.build_download();self.build_sidebar('download')

    def navigate(self,key):
        for view in list(reversed(self.subpages)):
            view.reject()
            self.finish_subpage(view)
        if key in ('mods','worlds','logs','resourcepacks','shaderpacks'):
            self.instance_tab=key;key='instance'
        self.current_page=key;self.back_button.setVisible(key!='home');self.stack.setCurrentWidget(self.page_map[key])
        titles={'home':'Onion  '+LAUNCHER_VERSION,'instance':'实例管理 · '+self.instances.display_name(self.selected_version),'versions':'实例列表','download':'下载','settings':'设置','about':'关于 Onion'}
        self.page_title=titles[key];self.title.setText(titles[key])
        if key=='instance':self.build_instance()
        elif key!='settings' or self.settings_editor is None:getattr(self,'build_'+key)()
        self.build_sidebar(key)

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
        menu=QMenu(self)
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
            if self.selected_version not in self.versions:self.selected_version=self.versions[0] if self.versions else ''
            self.selector.blockSignals(True);self.selector.clear()
            for vid in self.versions:self.selector.addItem(self.instances.display_name(vid),vid)
            if not self.versions:self.selector.addItem('尚未安装游戏','')
            self.selector.setCurrentIndex(max(0,self.selector.findData(self.selected_version)));self.selector.blockSignals(False)
            self.update_selection()
            self.config_obj.set('selected_version',self.selected_version)
            if refresh_page and self.current_page!='settings':self.navigate(self.current_page)
        self.tasks.submit(scan,done,self.error)

    def choose_version(self,index):
        vid=self.selector.itemData(index)
        if vid:self.set_selected(vid)

    def set_selected(self,vid,refresh_page=True):
        if vid not in self.versions:return False
        if vid!=self.selected_version and self.instance_editor and self.instance_editor.dirty:
            answer=QMessageBox.question(self,'实例设置尚未保存','切换实例前，是否保存当前实例的设置？',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Cancel:return False
            if answer==QMessageBox.StandardButton.Save:
                self.instance_editor.save()
                if self.instance_editor.dirty:return False
            self.instance_editor.dirty=False
        self.selected_version=vid;self.config_obj.set('selected_version',vid)
        self.selector.blockSignals(True);self.selector.setCurrentIndex(self.selector.findData(vid));self.selector.blockSignals(False)
        self.update_selection()
        if self.current_page=='instance':self.build_instance()
        elif self.current_page=='versions' and refresh_page:self.build_versions()
        return True

    def refresh_account(self):
        account=self.accounts.current()
        if self.account_button:
            self.account_button.setText(account.username if account else '添加账户')
            self.account_button.setSubtitle({'microsoft':'微软账户','authlib':'外置登录','offline':'离线模式'}.get(account.type,'') if account else 'Microsoft / 离线 / 外置')

    def open_accounts(self):
        from .accounts import AccountsDialog
        dialog=AccountsDialog(self);self.dialogs.append(dialog);self.show_subpage(dialog)

    def open_folder(self,path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def error(self,error):
        self.status.setText(str(error));QMessageBox.warning(self,'操作未完成',str(error))

    def task(self,title,work,done=None,mutates=True):
        if mutates and self.mutating:self.error('已有文件操作进行中，请等待完成或取消当前任务。');return
        if mutates:self.mutating=True
        dialog=TaskDialog(self,title);self.dialogs.append(dialog)
        def success(value):
            if mutates:self.mutating=False
            dialog.accept();self.status.setText(title+' · 完成')
            if done:done(value)
        def failure(error):
            if mutates:self.mutating=False
            dialog.accept()
            if dialog.job and dialog.job.cancel.is_set():self.status.setText('任务已取消')
            else:self.error(error)
        dialog.job=self.tasks.submit(work,success,failure,dialog.update_progress,self.repo.downloader)
        self.show_subpage(dialog);return dialog.job

    @Slot(str,bool)
    def append_log(self,text,is_error=False):
        self.logs.appendPlainText(text)

    @Slot(int)
    def exited(self,code):
        self.launch_pending=False
        if self.selected_version and self.started_at:self.instances.add_play_time(self.running_version,time.time()-self.started_at)
        self.started_at=0;self.status.setText(f'游戏已退出 · 代码 {code}')
        if self.config_obj.get('keep_launcher_open'):self.show();self.raise_()
        else:self.close()

    def closeEvent(self,event):
        editors=[self.settings_editor,self.instance_editor]
        if any(editor and editor.dirty for editor in editors):
            if QMessageBox.question(self,'尚未保存','关闭并放弃未保存的设置？')!=QMessageBox.StandardButton.Yes:event.ignore();return
            for editor in editors:
                if editor:editor.dirty=False
        if self.tasks.jobs:
            if QMessageBox.question(self,'后台任务仍在运行','取消后台任务并在结束后关闭启动器？')!=QMessageBox.StandardButton.Yes:event.ignore();return
            self.tasks.cancel_all();self.hide();event.ignore()
            self.close_timer=QTimer(self);self.close_timer.timeout.connect(lambda:self.close() if not self.tasks.jobs else None);self.close_timer.start(200)
            return
        event.accept()


def main():
    application=QApplication.instance() or QApplication(sys.argv)
    configure_fonts(application)
    application.setApplicationName(LAUNCHER_NAME);application.setStyle('Fusion')
    from ..log import setup_logging
    setup_logging(app_root()/'logs',to_console=False)
    window=MainWindow();window.show()
    return application.exec()
