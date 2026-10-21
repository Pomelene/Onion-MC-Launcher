"""Onion Minecraft Launcher Qt shell: HMCL-inspired navigation and native high-DPI rendering."""
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt,Signal,Slot,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QStackedWidget,QComboBox,
    QLineEdit,QPlainTextEdit,QMessageBox,QInputDialog,QDialog,QFormLayout,QCheckBox,QSpinBox)
from .widgets import STYLE,Page,Card,Empty,label,button,column,row,clear,icon,TaskDialog,configure_fonts
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
        self.setWindowTitle(f'{LAUNCHER_NAME} {LAUNCHER_VERSION}');self.resize(1280,820);self.setMinimumSize(1060,700)
        resource=Path(getattr(sys,'_MEIPASS',self.root))/'assets/craftbridge.ico'
        if resource.exists():self.setWindowIcon(QIcon(str(resource)))
        self.setStyleSheet(STYLE);self._build();self.game_log.connect(self.append_log);self.game_exit.connect(self.exited)
        self.refresh_account();self.navigate('home');QTimer.singleShot(0,self.reload_versions)

    def _build(self):
        shell=QWidget();outer=row(shell,0,0);self.setCentralWidget(shell)
        side=QWidget();side.setObjectName('sidebar');side.setFixedWidth(224);nav=column(side,18,7)
        brand=row();mark=label('O');mark.setStyleSheet('background:#277bd7;color:white;font-size:23px;font-weight:700;border-radius:10px;padding:7px 12px;')
        brand.addWidget(mark);text=column();text.addWidget(label('Onion','heading'));text.addWidget(label('MINECRAFT LAUNCHER','eyebrow'));brand.addLayout(text);nav.addLayout(brand);nav.addSpacing(25)
        self.nav={}
        for heading,items in [('游戏',[('home','开始游戏','home'),('versions','游戏实例','grid'),('download','下载中心','download')]),('内容',[('mods','模组与资源','package'),('worlds','世界存档','world')]),('启动器',[('logs','运行日志','history'),('settings','设置','settings')])]:
            nav.addSpacing(10);nav.addWidget(label(heading,'eyebrow'))
            for key,title,glyph in items:
                item=button(title,lambda k=key:self.navigate(k),'nav',glyph);item.setCheckable(True);self.nav[key]=item;nav.addWidget(item)
        nav.addStretch();nav.addWidget(button('打开游戏目录',lambda:self.open_folder(self.repo.game_dir),glyph='folder'))
        self.account_button=button('添加游戏账号',self.open_accounts,'soft','account');nav.addWidget(self.account_button)
        self.account_hint=label('Microsoft · 离线 · 外置','muted');self.account_hint.setAlignment(Qt.AlignmentFlag.AlignCenter);nav.addWidget(self.account_hint)
        outer.addWidget(side)
        main=QWidget();body=column(main,28,20);outer.addWidget(main,1)
        header=row();titles=column(spacing=3);self.title=label('开始游戏','title');self.subtitle=label('','muted');titles.addWidget(self.title);titles.addWidget(self.subtitle);header.addLayout(titles,1)
        self.selector=QComboBox();self.selector.setMinimumWidth(245);self.selector.setMaximumWidth(310);self.selector.currentIndexChanged.connect(self.choose_version)
        header.addWidget(self.selector);self.launch_button=button('启动游戏',self.launch_selected,'primary','play');header.addWidget(self.launch_button);body.addLayout(header)
        self.stack=QStackedWidget();self.page_map={};body.addWidget(self.stack,1)
        for key in self.nav:
            page=Page();self.page_map[key]=page;self.stack.addWidget(page)
        self.status=label('就绪','muted');body.addWidget(self.status)
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(3000)

    def navigate(self,key):
        self.current_page=key
        for name,item in self.nav.items():item.setChecked(name==key)
        self.stack.setCurrentWidget(self.page_map[key])
        meta={'home':('开始游戏','准备好，回到你的世界。'),'versions':('游戏实例','管理版本、加载器和独立实例。'),'download':('下载中心','发现新的内容，扩展你的世界。'),'mods':('模组与资源','按实例管理模组、资源包与光影。'),'worlds':('世界存档','珍藏每一次创造，随时备份与恢复。'),'logs':('运行日志','启动过程、游戏输出与崩溃诊断。'),'settings':('设置','游戏、Java、下载与账号。')}
        self.title.setText(meta[key][0]);self.subtitle.setText(meta[key][1]);getattr(self,'build_'+key)()

    def page(self,key):
        if key=='logs':self.logs.setParent(None)
        self.page_seq[key]=self.page_seq.get(key,0)+1
        page=self.page_map[key];clear(page.body);return page.body

    def reload_versions(self):
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
            self.launch_button.setText('启动游戏' if self.versions else '安装游戏')
            self.config_obj.set('selected_version',self.selected_version)
            self.navigate(self.current_page)
        self.tasks.submit(scan,done,self.error)

    def choose_version(self,index):
        vid=self.selector.itemData(index)
        if vid:self.set_selected(vid)

    def set_selected(self,vid):
        self.selected_version=vid;self.config_obj.set('selected_version',vid)
        self.selector.blockSignals(True);self.selector.setCurrentIndex(self.selector.findData(vid));self.selector.blockSignals(False)
        self.navigate(self.current_page)

    def refresh_account(self):
        account=self.accounts.current();self.account_button.setText(account.username if account else '添加游戏账号')
        self.account_hint.setText({'microsoft':'Microsoft 正版','authlib':'外置账号','offline':'离线身份'}.get(account.type,'') if account else 'Microsoft · 离线 · 外置')

    def open_accounts(self):
        from .accounts import AccountsDialog
        dialog=AccountsDialog(self);self.dialogs.append(dialog);dialog.open()

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
        dialog.open();return dialog.job

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
