"""Offscreen multi-root and embedded Java checks; no real JVM or game starts."""
import os,sys,json,time,tempfile,traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from launcher.config import Config
from launcher.instance import InstanceStore
from launcher.version_settings import VersionSettingsStore
from launcher.java import JavaInfo
from launcher.accounts import AccountRecord,offline_uuid
from launcher.storage import directory_key
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def hook(kind,value,tb):errors.append(str(value));traceback.print_exception(kind,value,tb)
sys.excepthook=hook
def wait(predicate):
    app.processEvents()
    end=time.monotonic()+20
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert predicate(),'Qt operation timed out'
    assert not errors,errors
def idle(window):wait(lambda:not window.tasks.jobs)
def snapshot(window,name):
    app.processEvents();image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);window.render(image)
    assert image.save(str(ROOT/'docs/screens'/name))

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='libraries-java-') as folder:
    base=Path(folder);path=base/'onionmcl.json';a=base/'生存客户端';b=base/'红石客户端'
    for root,versions in ((a,('same','survival')),(b,('same','creative'))):
        for vid in versions:
            version=root/'versions'/vid;version.mkdir(parents=True)
            (version/(vid+'.json')).write_text(json.dumps({'id':vid,'mainClass':'Main','libraries':[]}))
    config=Config(path);config.update({'game_dir':str(a),'selected_version':'same'})
    InstanceStore(path).update('same',name='生存 · Fabric')
    VersionSettingsStore(path).set('same',{'max_memory':6144,'isolate':False})
    window=MainWindow(path,base);window.error=lambda error:errors.append(str(error));window.show();idle(window)
    wait(lambda:len(window.versions)==2);assert window.instances.display_name('same')=='生存 · Fabric'
    window.navigate('versions');assert window.add_game_library(b);idle(window)
    assert window.repo.game_dir==b and window.version_settings.get('same')=={}
    window.instances.update('same',name='红石 · Fabric');window.version_settings.set('same',{'max_memory':2048,'isolate':True})
    window.set_selected('same');assert window.repo.run_dir('same')==b/'versions/same'
    assert window.switch_game_library(a);idle(window)
    assert window.selected_version=='same' and window.version_settings.get('same')['max_memory']==6144
    assert window.instances.display_name('same')=='生存 · Fabric' and window.repo.run_dir('same')==a
    # Folder rail actions exercise the actual UI callback.
    window.library_rail.buttons[directory_key(b)].click();idle(window)
    assert window.repo.game_dir==b and window.selected_version=='same'
    window.mutating=True;assert not window.switch_game_library(a);assert window.repo.game_dir==b;window.mutating=False
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        for width in (1100,1440):
            window.resize(width,900);app.processEvents();snapshot(window,f'qt-library-folders-{mode}-{width}.png')
            assert window.page_map['versions'].horizontalScrollBar().maximum()==0,'Library must fit the window'
    window.quick_select();picker=window.dialogs[-1]
    assert picker.library_choice.count()==2;picker.accept()
    # Use fixture runtime information; scanning must not launch a real Java process.
    fixture=JavaInfo(base/'java21/bin/java.exe',21,'21.0.8','x86_64',64)
    count=len(window.dialogs)
    with patch('launcher.java.find_all_java',return_value=[fixture]):
        window.manage_java();idle(window)
    editor=window.settings_editor;manager=editor.java_manager
    assert len(window.dialogs)==count and manager.isVisible() and not manager.isWindow(), (len(window.dialogs),count,manager.isVisible(),manager.isWindow(),editor.stack.currentIndex(),editor.tab_names,window.current_page)
    assert editor.stack.currentWidget() is manager and manager.tree.topLevelItemCount()==1
    manager.tree.setCurrentItem(manager.tree.topLevelItem(0));manager.use.click()
    assert Config(path).get('java_path')==str(fixture.path)
    assert window.version_settings.get('same')['max_memory']==2048
    runtime=JavaInfo(base/'java25/bin/java.exe',25,'25.0.1','x86_64',64)
    def download(*args):args[2]('正在下载测试运行时');args[3](50,100);return runtime
    with patch('launcher.java.download_java',side_effect=download):
        manager.download_java();assert manager.job and manager.progress.isVisible();idle(window)
    assert manager.job is None and not window.mutating and Config(path).get('java_path')==str(runtime.path)
    with patch('launcher.java.download_java',side_effect=RuntimeError('fixture download failed')):
        manager.download_java();idle(window)
    assert 'fixture download failed' in manager.status.text() and not window.subpages
    def slow(*args):time.sleep(.1);return fixture
    with patch('launcher.java.download_java',side_effect=slow):
        manager.download_java();manager.cancel_download();idle(window)
    assert manager.status.text()=='下载已取消' and Config(path).get('java_path')==str(runtime.path)
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance();snapshot(window,f'qt-java-embedded-{mode}.png')
    # Existing settings directory editor routes through the same scope switch.
    editor.fields['game_dir'].setText(str(a));assert editor.flush();idle(window)
    assert window.repo.game_dir==a and window.instances.display_name('same')=='生存 · Fabric'
    assert window.version_settings.get('same')['max_memory']==6144
    window.navigate('home');window.set_selected('same')
    account=AccountRecord('offline','Fixture',offline_uuid('Fixture'));window.accounts.add(account);window.accounts.set_current(account.uuid)
    process=SimpleNamespace(proc=SimpleNamespace(poll=lambda:None),stop=lambda:None)
    with patch.object(window.repo,'install',return_value=SimpleNamespace(java_major=21)),patch('launcher.java.probe_java',return_value=fixture),patch('launcher.java.resolve_java',return_value=fixture),patch('launcher.launch.launch',return_value=process):
        window.launch_selected();idle(window)
    assert window.process is process and window.instances.get('same').launch_count==1
    window.started_at=time.time()-10;assert window.switch_game_library(b);idle(window)
    assert window.instances.get('same').launch_count==0
    window.exited(0);assert window.instances.get('same').play_seconds==0
    assert InstanceStore(path,a,a).get('same').play_seconds>=10
    assert window.switch_game_library(a);idle(window);window.set_selected('survival')
    assert window.switch_game_library(b);idle(window);window.set_selected('same')
    window.close();idle(window)
    restored=MainWindow(path,base);restored.error=lambda error:errors.append(str(error));idle(restored)
    assert restored.repo.game_dir==b and restored.selected_version=='same'
    assert restored.switch_game_library(a);idle(restored);assert restored.selected_version=='survival'
    restored.game_libraries.remove(b);assert (b/'versions/same/same.json').is_file()
    restored.close();idle(restored);assert not errors,errors
print(json.dumps({'result':'pass','fixtures_only':True,'folder_scope':True,'remembered_selection':True,'java_embedded':True,'inline_download_cancel':True,'no_actual_game_or_java_launch':True}))
