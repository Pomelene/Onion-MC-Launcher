"""Offscreen Qt integration checks and deterministic preview artifacts.
Uses disposable data only; no desktop automation, network login or game launch.
"""
import os,sys,time,tempfile,json,traceback
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.deps/qt'))
from PySide6.QtCore import QThread,QTimer
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QPushButton
from launcher.config import Config
from launcher.instance import InstanceStore
from launcher.qtui.app import MainWindow
from launcher.qtui.accounts import AccountsDialog,MicrosoftLogin
from launcher.qtui.widgets import configure_fonts
from unittest.mock import patch
from launcher.auth.microsoft import DeviceCode,LoginCancelled

print('Initializing offscreen QApplication',flush=True)
app=QApplication([]);app.setStyle('Fusion');errors=[]
configure_fonts(app)
print('QApplication initialized',flush=True)
def exception_hook(kind,value,tb):
    errors.append(''.join(traceback.format_exception(kind,value,tb)));traceback.print_exception(kind,value,tb)
sys.excepthook=exception_hook

def pump(predicate,seconds=8):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert predicate(),'Qt task did not finish before deadline'

def render(widget,name):
    app.processEvents();image=QImage(widget.size()*2,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(2);image.fill(0)
    widget.render(image);image.save(str(ROOT/'docs/screens'/name))

(ROOT/'docs/screens').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-smoke-') as tmp:
    base=Path(tmp);config=Config(base/'config/settings.json');config.set('game_dir',str(base/'minecraft'))
    for vid,libs in [('1.21.1',[]),('1.21.1-Fabric-My-World',[{'name':'net.fabricmc:fabric-loader:0.16.0'}])]:
        directory=base/'minecraft/versions'/vid;directory.mkdir(parents=True)
        (directory/(vid+'.json')).write_text(json.dumps({'id':vid,'mainClass':'Main','libraries':libs}),encoding='utf-8')
    instances=InstanceStore(base/'config/instances.json');instances.update('1.21.1-Fabric-My-World',name='与朋友一起探索 · Minecraft 生存世界')
    print('Constructing main window',flush=True)
    window=MainWindow(config.path,base);window.error=lambda error:errors.append(str(error));window.show()
    pump(lambda:len(window.versions)==2 and not window.tasks.jobs)
    print('Rendering home',flush=True)
    render(window,'qt-home.png')
    for page in ('versions','download','mods','worlds','logs','logs','settings','home'):
        window.navigate(page);pump(lambda:not window.tasks.jobs)
        if page in ('versions','download','settings'):render(window,'qt-'+page+'.png')
    accounts=AccountsDialog(window);accounts.show();render(accounts,'qt-accounts.png')
    entry=next(b for b in accounts.findChildren(QPushButton) if b.text()=='微软正版登录')
    with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
        entry.click();app.processEvents()
    assert isinstance(accounts.login,MicrosoftLogin) and accounts.login.isVisible()
    assert callable(accounts.login.open),'QDialog.open must not be shadowed by a widget'
    assert accounts.login.advanced.isHidden() and not accounts.login.client.isVisible()
    assert '此版本尚未启用正版登录' in accounts.login.code.text()
    render(accounts.login,'qt-microsoft.png');accounts.login.reject()
    with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
        accounts.relogin();app.processEvents();assert accounts.login.isVisible();accounts.login.reject();accounts.accept()
    ready=MicrosoftLogin(accounts,'00000000-0000-4000-8000-000000000001');ready.show()
    assert ready.client.text()=='00000000-0000-4000-8000-000000000001' and ready.advanced.isHidden()
    render(ready,'qt-microsoft-ready.png');ready.reject()
    # Full success and cancellation wiring without contacting Microsoft.
    delivered=[]
    login=MicrosoftLogin(accounts,'00000000-0000-4000-8000-000000000001',delivered.append)
    def fake_login(client,on_code,cancel,on_step):
        on_code(DeviceCode('ABCD-EFGH','https://microsoft.com/link','private-device',900,5,''))
        on_step('正在读取玩家档案')
        return {'username':'Player','uuid':'a'*32,'access_token':'fake-access','refresh_token':'fake-refresh','expires_at':9999999999,'xuid':''}
    with patch('launcher.qtui.accounts.login_with_device_code',side_effect=fake_login),patch('launcher.qtui.accounts.QDesktopServices.openUrl',return_value=True) as opened:
        login.begin();pump(lambda:bool(delivered))
        assert opened.call_count==1,'authorization page must open automatically once'
    assert delivered[0]['client_id']=='00000000-0000-4000-8000-000000000001'
    prevented=[]
    login=MicrosoftLogin(accounts,'00000000-0000-4000-8000-000000000001',prevented.append)
    def cancelled_login(client,on_code,cancel,on_step):
        while not cancel():time.sleep(.005)
        raise LoginCancelled()
    with patch('launcher.qtui.accounts.login_with_device_code',side_effect=cancelled_login):
        login.begin();login.reject();pump(lambda:not window.tasks.jobs)
    assert not prevented,'cancelled login saved an account'
    login=MicrosoftLogin(accounts,'00000000-0000-4000-8000-000000000001')
    with patch('launcher.qtui.accounts.QDesktopServices.openUrl',return_value=False):
        login.progress(('code',DeviceCode('ABCD-EFGH','https://microsoft.com/link','private-device',900,5,'')))
        assert '浏览器未能自动打开' in login.status.text() and login.open_button.isEnabled()
    login.reject()
    # Real account-management entry automatically starts, opens the browser, and
    # saves only after the mocked backend completes. No real browser/network.
    config.set('microsoft_client_id','00000000-0000-4000-8000-000000000001')
    with patch('launcher.qtui.accounts.login_with_device_code',side_effect=fake_login),patch('launcher.qtui.accounts.QDesktopServices.openUrl',return_value=True) as opened:
        accounts.microsoft();pump(lambda:bool(window.accounts.accounts))
        assert window.accounts.accounts[0].username=='Player' and opened.call_count==1
    config.set('microsoft_client_id','')
    # The new Qt action must still use the managed inheritance-only instance path.
    with patch('launcher.qtui.actions.QInputDialog.getText',return_value=('Qt-Temporary-Instance',True)):
        window.create_instance();pump(lambda:not window.tasks.jobs)
    assert 'Qt-Temporary-Instance' in window.repo.list_installed()
    assert (window.repo.version_dir('Qt-Temporary-Instance')/'.isolate').is_file()

    beats=[0];received=[]
    timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:beats.__setitem__(0,beats[0]+1));timer.start()
    def work(job):
        assert QThread.currentThread()!=app.thread()
        job.emit('background');job.cancel.wait(.4);return 'done'
    window.tasks.submit(work,lambda result:received.append((result,QThread.currentThread()==app.thread())))
    pump(lambda:bool(received));timer.stop()
    assert received==[('done',True)] and beats[0]>=10,(received,beats)
    cancelled=[]
    def cancellable(job):job.cancel.wait(2);return job.cancel.is_set()
    job=window.tasks.submit(cancellable,lambda result:cancelled.append(result));job.cancel.set();pump(lambda:bool(cancelled));assert cancelled==[True]
    assert not errors,errors
    window.close();app.processEvents()
    report={'result':'pass','backend':'Qt 6 / PySide6','fixture_only':True,'desktop_input':False,'network_auth':False,'pages':['home','versions','download','mods','worlds','logs','settings'],'login_success_and_cancel_mocked':True,'main_thread_callbacks':True,'event_loop_heartbeats':beats[0],'cancellation':True,'visual_artifacts':'docs/screens/qt-*.png'}
    report.update(microsoft_entry_click=True,maintainer_settings_hidden=True,automatic_browser_mocked=True,browser_failure_fallback=True,automatic_account_save_mocked=True)
    (ROOT/'docs/qt-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
