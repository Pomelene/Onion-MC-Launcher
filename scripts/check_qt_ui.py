"""Offscreen Qt integration checks and deterministic preview artifacts.
Uses disposable data only; no desktop automation, network login or game launch.
"""
import os,sys,time,tempfile,json,traceback
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.deps/qt'))
from PySide6.QtCore import QThread,QTimer,QCoreApplication,QEvent
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox
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
    app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
    image=QImage(widget.size()*2,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(2);image.fill(0)
    widget.render(image)
    assert image.pixelColor(image.width()//2,image.height()//2).alpha()>0,('empty render',name)
    image.save(str(ROOT/'docs/screens'/name))

(ROOT/'docs/screens').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-smoke-') as tmp:
    base=Path(tmp);config=Config(base/'config/settings.json');config.set('game_dir',str(base/'minecraft'))
    for vid,libs in [('1.21.1',[]),('1.21.1-Fabric-My-World',[{'name':'net.fabricmc:fabric-loader:0.16.0'}])]:
        directory=base/'minecraft/versions'/vid;directory.mkdir(parents=True)
        (directory/(vid+'.json')).write_text(json.dumps({'id':vid,'mainClass':'Main','libraries':libs}),encoding='utf-8')
    instances=InstanceStore(base/'config/instances.json');instances.update('1.21.1-Fabric-My-World',name='与朋友一起探索 · Minecraft 生存世界')
    print('Constructing main window',flush=True)
    window=MainWindow(config.path,base);window.error=lambda error:errors.append(str(error));window.show()
    config=window.config_obj
    pump(lambda:len(window.versions)==2 and not window.tasks.jobs)
    print('Rendering home',flush=True)
    render(window,'qt-home.png')
    for page in ('versions','download','mods','worlds','logs','logs','settings','home'):
        window.navigate(page);pump(lambda:not window.tasks.jobs)
        if page in ('versions','download','settings'):render(window,'qt-'+page+'.png')
    # Settings drafts survive navigation; browsing never commits or discards them.
    window.navigate('settings');editor=window.settings_editor
    previous=config.get('max_memory');editor.fields['max_memory'].setValue(6144);editor.select_tab(1)
    window.navigate('home');window.navigate('settings')
    assert window.settings_editor is editor and editor.dirty and config.get('max_memory')==previous
    editor.save();pump(lambda:not window.tasks.jobs)
    assert config.get('max_memory')==6144 and editor.stack.currentIndex()==1 and not editor.dirty
    vid=window.selected_version;window.instance_settings(vid);instance_editor=window.instance_editor
    assert not instance_editor.fields['max_memory'].isEnabled() and instance_editor.stack.isEnabled()
    instance_editor.specific.setChecked(True);instance_editor.fields['max_memory'].setValue(8192)
    window.navigate('worlds');pump(lambda:not window.tasks.jobs);window.navigate('instance')
    window.instance_workspace.open_tab('game')
    assert window.instance_editor is instance_editor and instance_editor.dirty
    instance_editor.save();pump(lambda:not window.tasks.jobs)
    assert window.version_settings.resolve(vid,config)['max_memory']==8192
    render(window,'qt-instance-settings.png')
    instance_editor.specific.setChecked(False);instance_editor.save();pump(lambda:not window.tasks.jobs)
    assert window.version_settings.get(vid)=={} and window.version_settings.resolve(vid,config)['max_memory']==6144
    # Complete list and quick picker change the same selected instance without launching.
    window.navigate('versions');query=window.library_search
    query.setText('Fabric');assert window.version_tree.topLevelItemCount()==1
    window.navigate('home');window.quick_select();picker=window.dialogs[-1]
    picker.query.setText('1.21.1');item=picker.tree.topLevelItem(0);target=item.data(0,__import__('PySide6.QtCore',fromlist=['Qt']).Qt.ItemDataRole.UserRole)
    picker.choose(item);assert window.selected_version==target and not window.process
    window.navigate('versions');assert window.version_tree.topLevelItemCount()==1
    window.open_content_download('shaderpacks');assert window.download_kind=='shader'
    # A modpack creates a new instance even when no existing target was chosen.
    from unittest.mock import Mock
    with patch('launcher.catalog.versions',return_value=[]),patch('launcher.catalog.pick_version',return_value={'id':'fixture'}),patch('launcher.catalog.download_version',side_effect=lambda downloader,version,target:target/'fixture.mrpack') as downloaded,patch('launcher.modpack.import_modpack',return_value='new-pack'),patch.object(window,'installed') as installed:
        window.install_project('fixture','modpack','','',version_id='');pump(lambda:not window.tasks.jobs)
        assert installed.call_args.args==('new-pack',)
        assert downloaded.call_args.args[2]==window.repo.game_dir/'.cache/modpacks'
    # A custom background is read locally and does not change the game library.
    original_library=window.repo.game_dir;background=QImage(160,90,QImage.Format.Format_RGB32);background.fill(0xff527a6b);background.save(str(base/'wallpaper.png'))
    editor.fields['background_image'].setText(str(base/'wallpaper.png'));editor.save();pump(lambda:not window.tasks.jobs)
    window.navigate('home');canvas=window.page_map['home'].findChildren(__import__('launcher.qtui.widgets',fromlist=['HomeCanvas']).HomeCanvas)[-1]
    assert canvas.image is not None and window.repo.game_dir==original_library
    # Installer filtering and cancellation never install or launch a game.
    from launcher.version import VersionManifest
    manifest=VersionManifest({'versions':[{'id':'1.21.1','type':'release'},{'id':'24w14a','type':'snapshot'}]})
    with patch.object(window.repo,'fetch_manifest',return_value=manifest):
        window.install_dialog();installer=window.dialogs[-1]
        pump(lambda:not installer.loading and installer.tree.topLevelItemCount()==1)
    assert installer.version.text()=='1.21.1'
    installer.snapshots.setChecked(True);assert installer.tree.topLevelItemCount()==2
    installer.query.setText('24w');assert installer.tree.topLevelItemCount()==1
    installer.loader.setCurrentIndex(1);assert installer.build.isEnabled()
    render(installer,'qt-install.png');installer.reject()
    for size in ((1100,740),(1920,1080)):
        window.resize(*size);app.processEvents();assert window.width()==size[0],('unexpected minimum size',window.size())
        window.navigate('settings');render(window,f'qt-settings-{size[0]}.png')
        assert all(item.width()>=200 for item in window.nav.values()),'Sidebar labels are clipped'
        for field in window.settings_editor.fields.values():
            if hasattr(field,'lineEdit') and field.isVisible() and field.lineEdit():
                assert field.lineEdit().width()>=100,'Numeric editor was collapsed by the style'
    window.resize(1440,900);window.navigate('home')
    window.open_accounts();embedded_accounts=window.dialogs[-1]
    assert not embedded_accounts.isWindow() and window.stack.currentWidget() is embedded_accounts
    with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
        embedded_accounts.microsoft()
    embedded_login=embedded_accounts.login
    assert not embedded_login.isWindow() and window.stack.currentWidget() is embedded_login
    render(window,'qt-inline-login.png');window.go_back()
    assert embedded_login.closed and not embedded_login.timer.isActive() and window.stack.currentWidget() is embedded_accounts
    window.go_back();assert not window.subpages
    from launcher.mods import ModInfo
    from launcher.qtui.widgets import ContentRow
    window.navigate('mods');pump(lambda:not window.tasks.jobs)
    content_dir=window.repo.run_dir(window.selected_version)/'mods';content_dir.mkdir(parents=True,exist_ok=True)
    fixtures=[ModInfo(content_dir/f'fabric-api-{i}.jar',f'Fabric API 示例 {i}','0.120.0','fabric-api',i!=1) for i in range(12)]
    import zipfile
    artwork=QImage(32,32,QImage.Format.Format_RGB32);artwork.fill(0xff20c080);artwork.save(str(base/'fixture-icon.png'))
    for info in fixtures:
        with zipfile.ZipFile(info.path,'w') as archive:
            archive.writestr('fabric.mod.json',json.dumps({'id':'fabric-api','name':info.name,'version':info.version,'icon':'assets/icon.png'}))
            archive.writestr('assets/icon.png',(base/'fixture-icon.png').read_bytes())
    with patch('launcher.mods.scan_mods',return_value=fixtures):
        window.instance_workspace.open_tab('mods');pump(lambda:not window.tasks.jobs)
    rows=window.instance_content.findChildren(ContentRow)
    assert len(rows)==12 and all(r.height()==64 for r in rows)
    titles=[r.text.title for r in rows];assert titles==sorted(titles,key=str.casefold)
    assert rows[0].image.pixmap().toImage().pixelColor(8,8).green()>150
    before_page=window.stack.currentWidget();before_rows=list(rows);old_subpages=list(window.subpages)
    for _ in range(2):
        previous=rows[0].check.isChecked();rows[0].check.click();pump(lambda:not window.tasks.jobs)
        assert rows[0].check.isChecked()!=previous and window.stack.currentWidget() is before_page
        assert window.subpages==old_subpages and window.instance_content.findChildren(ContentRow)==before_rows
    with patch('launcher.mods.set_mod_enabled',side_effect=OSError('fixture failure')):
        previous=rows[0].check.isChecked();rows[0].check.click();pump(lambda:not window.tasks.jobs)
        assert rows[0].check.isChecked()==previous and rows[0].check.isEnabled()
    render(window,'qt-compact-mods.png')
    search=next(e for e in window.instance_content.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLineEdit']).QLineEdit) if e.placeholderText().startswith('搜索名称'))
    search.setText('示例 11');assert sum(not r.isHidden() for r in rows)==1
    window.navigate('home')
    import threading
    progress_ready=threading.Event();progress_release=threading.Event()
    def progress_work(job):
        job.emit('正在下载游戏资源');job.emit((3,10));progress_ready.set()
        progress_release.wait(5)
    progress_job=window.task('进度测试',progress_work)
    pump(lambda:progress_ready.is_set() and window.task_progress.value()==300)
    assert window.task_amount.text().endswith('30%')
    window.navigate('versions');assert not progress_job.cancel.is_set() and window.task_strip.isVisible()
    window.cancel_active_task();assert progress_job.cancel.is_set() and not window.task_cancel.isEnabled()
    progress_release.set();pump(lambda:not window.tasks.jobs);assert window.active_task is None and not window.task_strip.isVisible()
    window.navigate('home')
    accounts=AccountsDialog(window);accounts.show();render(accounts,'qt-accounts.png')
    entry=next(b for b in accounts.findChildren(QPushButton) if b.text()=='微软正版登录')
    with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
        entry.click();app.processEvents()
    assert isinstance(accounts.login,MicrosoftLogin) and accounts.login.isVisible()
    assert callable(accounts.login.open),'QDialog.open must not be shadowed by a widget'
    assert not accounts.login.client.isVisible() and not any('维护者设置' in b.text() for b in accounts.login.findChildren(QPushButton))
    assert '此版本尚未启用正版登录' in accounts.login.code.text()
    render(accounts.login,'qt-microsoft.png');accounts.login.reject()
    with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
        accounts.relogin();app.processEvents();assert accounts.login.isVisible();accounts.login.reject();accounts.accept()
    ready=MicrosoftLogin(accounts,'00000000-0000-4000-8000-000000000001');ready.show()
    assert ready.client.text()=='00000000-0000-4000-8000-000000000001' and not ready.client.isVisible()
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
    report={'result':'pass','backend':'Qt 6 / PySide6','fixture_only':True,'desktop_input':False,'network_auth':False,'pages':['home','instance','versions','download','settings','about'],'login_success_and_cancel_mocked':True,'main_thread_callbacks':True,'event_loop_heartbeats':beats[0],'cancellation':True,'visual_artifacts':'docs/screens/qt-*.png'}
    report.update(microsoft_entry_click=True,maintainer_settings_hidden=True,automatic_browser_mocked=True,browser_failure_fallback=True,automatic_account_save_mocked=True)
    report.update(settings_drafts_and_save=True,instance_override_inheritance=True,quick_picker_and_list_consistent=True,local_background=True,installer_filters_fixture=True,layouts=[1100,1440,1920])
    (ROOT/'docs/qt-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
