"""Account dialogs. Credentials stay in backend records, never in UI status strings."""
import time
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QWidget,QLineEdit,QFormLayout,QTreeWidget,
    QTreeWidgetItem,QInputDialog,QMessageBox,QDialogButtonBox)
from .widgets import label,button,column,row,Card
from ..accounts import AccountRecord,offline_uuid,validate_username
from ..auth.microsoft import login_with_device_code,verification_url,LoginCancelled
from ..auth.application import resolve_client_id,valid_client_id

HELP_URL='https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code'


class MicrosoftLogin(QDialog):
    def __init__(self,owner,client_id='',on_success=None):
        super().__init__(owner);self.owner=owner;self.tasks=owner.tasks;self.config=owner.config_obj
        self.on_success=on_success;self.job=None;self.closed=False;self.deadline=0;self.uri=''
        self.setWindowTitle('Microsoft · 登录 Minecraft Java 版');self.resize(610,490);self.setModal(True)
        body=column(self,26,16)
        body.addWidget(label('使用 Microsoft 账号登录','title'))
        body.addWidget(label('在你自己的浏览器中完成授权，启动器不会读取或保存微软密码。','muted',True))
        self.client=QLineEdit(resolve_client_id(self.config,client_id))
        self.client.setPlaceholderText('维护者提供的 Microsoft 应用 ID')
        self.advanced=Card('维护者设置');self.advanced.body.addWidget(self.client)
        self.advanced.body.addWidget(label('发布者只需配置一次登录应用，玩家无需注册。此处仅用于开发或更换应用。','muted',True))
        self.advanced.body.addWidget(button('应用配置说明',lambda:QDesktopServices.openUrl(QUrl(HELP_URL))))
        self.advanced.body.addWidget(button('Minecraft 应用访问申请',lambda:QDesktopServices.openUrl(QUrl('https://aka.ms/mce-reviewappid'))))
        body.addWidget(button('维护者设置',lambda:self.advanced.setVisible(self.advanced.isHidden())))
        body.addWidget(self.advanced);self.advanced.hide()
        code=Card();self.code=label('准备连接 Microsoft','heading');self.code.setStyleSheet('font-size:25px;letter-spacing:2px;color:#b8e8ee;')
        self.status=label('启动器会打开微软网页。输入授权码并同意授权后，返回这里即可。','muted',True)
        if not self.client.text():
            self.code.setText('此版本尚未启用正版登录')
            self.status.setText('发布者尚未配置登录服务，请联系启动器维护者获取支持正版登录的版本。你无需注册开发者应用。')
        code.body.addWidget(self.code);code.body.addWidget(self.status)
        actions=row();self.copy=button('复制授权码',self.copy_code);self.open_button=button('打开微软授权页',self.open_browser,'soft')
        self.copy.setEnabled(False);self.open_button.setEnabled(False);actions.addWidget(self.copy);actions.addWidget(self.open_button);actions.addStretch();code.body.addLayout(actions)
        body.addWidget(code);self.time_label=label('','muted');body.addWidget(self.time_label)
        body.addStretch();footer=row();self.cancel=button('取消',self.reject);self.start=button('登录 Microsoft',self.begin,'primary','account')
        footer.addStretch();footer.addWidget(self.cancel);footer.addWidget(self.start);body.addLayout(footer)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(500)

    def begin(self):
        if self.job or self.closed:return
        client_id=self.client.text().strip()
        if not valid_client_id(client_id):
            self.status.setText('此版本尚未配置有效的登录应用，请联系启动器维护者。普通玩家无需填写应用 ID。');return
        self.config.set('microsoft_client_id',client_id)
        self.start.setEnabled(False);self.client.setEnabled(False);self.copy.setEnabled(False);self.open_button.setEnabled(False)
        self.code.setText('正在获取…');self.status.setText('正在连接微软认证服务');self.deadline=0;self.uri=''
        def work(job):
            data=login_with_device_code(client_id,lambda code:job.emit(('code',code)),job.cancel.is_set,
                                        lambda text:job.emit(('step',text)))
            data['client_id']=client_id
            return data
        self.job=self.tasks.submit(work,self.login_completed,self.failed,self.progress)

    def progress(self,value):
        if self.closed:return
        kind,data=value
        if kind=='code':
            self.code.setText(data.user_code);self.uri=data.verification_uri
            self.deadline=time.monotonic()+data.expires_in;self.copy.setEnabled(True);self.open_button.setEnabled(True)
            self.status.setText('请在微软授权页输入此代码。完成后会自动验证 Xbox 与 Java 版玩家档案。')
            self.open_browser()
        else:self.status.setText(data)

    def tick(self):
        if self.deadline and not self.closed:
            seconds=max(0,int(self.deadline-time.monotonic()))
            self.time_label.setText(f'授权码有效时间  {seconds//60:02d}:{seconds%60:02d}')

    def copy_code(self):
        if self.copy.isEnabled():QApplication.clipboard().setText(self.code.text())

    def open_browser(self):
        if self.uri:
            try:opened=QDesktopServices.openUrl(QUrl(verification_url(self.uri)))
            except Exception:
                self.status.setText('无法打开微软授权页，请重新获取授权码。');return
            if not opened:self.status.setText('浏览器未能自动打开，请点击“打开微软授权页”重试，或在浏览器访问 microsoft.com/link 并输入上方代码。')

    def login_completed(self,data):
        self.job=None
        if self.closed:return
        self.timer.stop()
        if self.on_success:self.on_success(data)
        self.accept()

    def failed(self,error):
        self.job=None
        if self.closed:return
        self.deadline=0;self.time_label.setText('');self.code.setText('可以重新获取授权码')
        self.status.setText(str(error));self.start.setText('重新获取');self.start.setEnabled(True)
        if getattr(error,'code','') in ('minecraft_forbidden','invalid_app_registration'):
            self.code.setText('Minecraft 服务暂未允许登录')
            self.status.setText(str(error)+'。这不代表玩家没有购买游戏；普通玩家请联系启动器维护者。')
            self.start.setText('重试登录')
        self.client.setEnabled(True);self.copy.setEnabled(False);self.open_button.setEnabled(False)

    def reject(self):
        self.closed=True;self.timer.stop()
        if self.job:self.job.cancel.set()
        super().reject()


class AccountsDialog(QDialog):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.tasks=app.tasks;self.config_obj=app.config_obj;self.store=app.accounts
        self.setWindowTitle('账号管理');self.resize(780,540);self.setModal(True);body=column(self,24,16)
        body.addWidget(label('你的游戏身份','title'))
        body.addWidget(label('正版账号用于在线验证；离线账号仅提供本地玩家身份。','muted'))
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['玩家','账号类型','状态']);self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0,260);self.tree.setColumnWidth(1,140);body.addWidget(self.tree,1)
        actions=row();actions.addWidget(button('微软正版登录',self.microsoft,'primary','account'))
        actions.addWidget(button('添加离线账号',self.offline));actions.addWidget(button('外置登录',self.authlib));actions.addStretch();body.addLayout(actions)
        actions=row();actions.addWidget(button('设为当前',self.set_current,'soft'));actions.addWidget(button('验证 / 续期',self.refresh))
        actions.addWidget(button('重新登录',self.relogin));actions.addStretch();actions.addWidget(button('移除账号',self.remove,'danger'));actions.addWidget(button('完成',self.accept));body.addLayout(actions)
        self.status=label('','muted',True);body.addWidget(self.status);self.reload()
        self.finished.connect(lambda _:app.refresh_account())

    def reload(self):
        self.tree.clear()
        for account in self.store.accounts:
            kind={'microsoft':'Microsoft 正版','authlib':'外置账号'}.get(account.type,'离线账号')
            state='需要重新登录' if account.type!='offline' and not account.access_token or account.type=='microsoft' and not account.refresh_token else '需要续期' if account.is_expired() else '已登录' if account.type!='offline' else '本地身份'
            name=account.username+(' · 当前' if account.uuid==self.store.current_uuid else '')
            item=QTreeWidgetItem([name,kind,state]);item.setData(0,Qt.ItemDataRole.UserRole,account.uuid);self.tree.addTopLevelItem(item)
        if not self.store.accounts:self.status.setText('尚未添加账号。选择“微软正版登录”或先添加一个离线身份。')

    def selected(self):
        item=self.tree.currentItem()
        return self.store.get(item.data(0,Qt.ItemDataRole.UserRole)) if item else None

    def microsoft(self,client_id=''):
        self.login=MicrosoftLogin(self,client_id,self.saved)
        if getattr(self,'embedded',False):self.app.show_subpage(self.login)
        else:self.login.open()
        if self.login.client.text():QTimer.singleShot(0,self.login.begin)

    def saved(self,data):
        account=AccountRecord(type='microsoft',user_type='msa',**data)
        self.store.add(account);self.store.set_current(account.uuid);self.reload();self.status.setText(f'{account.username} 已登录 Minecraft Java 版。')

    def offline(self):
        if getattr(self,'embedded',False):
            dialog=QDialog(self);dialog.setWindowTitle('添加离线账户');body=column(dialog,24,16)
            body.addWidget(label('离线玩家身份','title'));field=QLineEdit();field.setPlaceholderText('3–16 位字母、数字或下划线');body.addWidget(field)
            status=label('','muted');body.addWidget(status)
            def save():
                name=field.text().strip();error=validate_username(name)
                if error:status.setText(error);return
                account=AccountRecord('offline',name,offline_uuid(name),access_token='0')
                self.store.add(account);self.store.set_current(account.uuid);self.reload();self.app.refresh_account();dialog.accept()
            controls=row();controls.addWidget(button('返回',dialog.reject));controls.addWidget(button('添加账户',save,'primary'));controls.addStretch();body.addLayout(controls);body.addStretch()
            self.app.show_subpage(dialog);return
        name,ok=QInputDialog.getText(self,'离线账号','玩家名称（3–16 位字母、数字或下划线）')
        if not ok:return
        error=validate_username(name)
        if error:QMessageBox.warning(self,'玩家名无效',error);return
        name=name.strip();account=AccountRecord('offline',name,offline_uuid(name),access_token='0')
        self.store.add(account);self.store.set_current(account.uuid);self.reload()

    def set_current(self):
        account=self.selected()
        if account:self.store.set_current(account.uuid);self.reload();self.app.refresh_account()

    def refresh(self):
        account=self.selected()
        if not account:return
        if account.type!='microsoft':self.status.setText('此操作用于 Microsoft 正版账号。');return
        if getattr(self,'refreshing',False):return
        self.refreshing=True;self.status.setText('正在验证 Microsoft、Xbox 与 Minecraft 玩家档案…')
        def done(value):
            self.refreshing=False;self.reload();self.status.setText(f'{value.username} 已续期。');self.app.refresh_account()
        def failed(error):self.refreshing=False;self.status.setText(str(error))
        self.tasks.submit(lambda job:self.store.refresh(account),done,failed)

    def relogin(self):
        account=self.selected()
        if account and account.type=='microsoft':self.microsoft(account.client_id)
        else:self.microsoft()

    def remove(self):
        account=self.selected()
        if account and QMessageBox.question(self,'移除账号',f'从启动器移除 {account.username}？\n不会删除微软账号或游戏文件。')==QMessageBox.StandardButton.Yes:
            self.store.remove(account.uuid);self.reload();self.app.refresh_account()

    def authlib(self):
        dialog=QDialog(self);dialog.setWindowTitle('外置验证服务器');body=column(dialog,24)
        form=QFormLayout();server=QLineEdit(self.config_obj.get('authlib_url') or '');server.setPlaceholderText('https://验证服务器')
        user=QLineEdit();password=QLineEdit();password.setEchoMode(QLineEdit.EchoMode.Password)
        for text,field in (('服务器',server),('用户名',user),('密码',password)):form.addRow(text,field)
        body.addLayout(form);status=label('密码仅用于本次认证，不会保存。','muted',True);body.addWidget(status)
        start=button('登录',role='primary');body.addWidget(start)
        def begin():
            from urllib.parse import urlparse
            parsed=urlparse(server.text().strip())
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:status.setText('请输入有效的 HTTPS 服务器地址');return
            if not user.text().strip() or not password.text():status.setText('请填写用户名和密码');return
            from ..auth.authlib import authenticate
            address,username,secret=server.text().strip(),user.text().strip(),password.text();password.clear();start.setEnabled(False)
            def done(data):
                record=AccountRecord(type='authlib',**data);self.store.add(record);self.store.set_current(record.uuid);self.reload();dialog.accept()
            def failed(error):status.setText(str(error));start.setEnabled(True)
            self.tasks.submit(lambda job:authenticate(address,username,secret),done,failed)
        start.clicked.connect(begin);self.auth_dialog=dialog
        if getattr(self,'embedded',False):self.app.show_subpage(dialog)
        else:dialog.open()
