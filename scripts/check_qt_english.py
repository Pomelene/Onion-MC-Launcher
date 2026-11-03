"""Offline bilingual smoke checks using disposable settings and game profiles."""
import json,os,sys,tempfile,time,re
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QLabel,QAbstractButton,QWidget
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.i18n import tr
from launcher.qtui.widgets import configure_fonts
app=QApplication([]);app.setStyle('Fusion');configure_fonts(app)
errors=[]
def capture(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=capture
def wait(window):
    deadline=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<deadline:QTest.qWait(10)
    assert not window.tasks.jobs,'task timeout'
    assert not errors,errors
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-english-') as directory:
    root=Path(directory);path=root/'onionmcl.json'
    Config(path).update({'language':'en-US','game_dir':str(root/'game'),'check_launcher_updates':False})
    name='自定义实例名称'
    folder=root/'game/versions'/name;folder.mkdir(parents=True)
    (folder/(name+'.json')).write_text(json.dumps({'id':name,'mainClass':'Main','libraries':[]}),encoding='utf-8')
    with patch('launcher.catalog.search',return_value={'hits':[],'total_hits':0}), patch('launcher.java.find_all_java',return_value=[]):
        window=MainWindow(path,root);window.show();QTest.qWait(50);wait(window)
        window.set_selected(name)
        assert tr('设置')=='Settings'
        assert name in window.versions
        for page in ('versions','settings','about','download','instance','tools'):
            window.navigate(page);QTest.qWait(30);wait(window)
            untranslated=[w.text() for w in window.findChildren(QWidget) if isinstance(w,(QLabel,QAbstractButton)) and w.isVisible() and re.search('[\u4e00-\u9fff]',w.text()) and name not in w.text()]
            assert not untranslated,(page,untranslated)
        window.navigate('settings');editor=window.settings_editor
        assert 'Global game settings' in editor.tab_names
        assert editor.fields['language'].currentData()=='en-US'
        for key in ('language','color_mode','background_mode','process_priority'):
            field=editor.fields[key]
            assert not any(re.search('[\u4e00-\u9fff]',field.itemText(i)) for i in range(field.count()) if field.itemData(i)!='zh-CN'),key
        for index in range(editor.stack.count()):
            editor.select_tab(index);QTest.qWait(5)
        window.resize(1280,850)
        editor.select_tab(editor.tab_names['Appearance']);app.processEvents()
        assert window.grab().save(str(ROOT/'tmp/english-settings.png'))
        editor.fields['max_memory'].setValue(6144);QTest.qWait(550);wait(window)
        assert Config(path).get('max_memory')==6144
        assert Config(path).get('language')=='en-US'
        # Switch both ways without recreating the window, including a live task.
        import threading
        release=threading.Event();completed=[]
        task=window.tasks.submit(lambda job:release.wait(5),lambda result:completed.append(result),lambda error:errors.append(str(error)))
        original_tasks=window.tasks;original_log=window.logs
        for locale,title in [('zh-CN','全局游戏设置'),('en-US','Global game settings'),('zh-CN','全局游戏设置')]:
            field=window.settings_editor.fields['language'];field.setCurrentIndex(field.findData(locale))
            QTest.qWait(650)
            assert title in window.settings_editor.tab_names,(locale,window.settings_editor.tab_names)
            assert window.settings_editor.stack.currentIndex()==editor.tab_names['Appearance']
            assert window.tasks is original_tasks and window.logs is original_log
            assert name==window.selected_version
            assert not release.is_set()
            assert Config(path).get('language')==locale
        release.set();wait(window);assert completed==[True]
        window.navigate('tools');QTest.qWait(30);wait(window)
        assert window.nav['skins'].text()=='皮肤管理'
        assert not errors,errors
        window.close();app.processEvents()
        Config(path).update({'language':'zh-CN'})
        window=MainWindow(path,root);window.show();QTest.qWait(50);wait(window)
        assert tr('设置')=='设置'
        window.navigate('settings');assert '全局游戏设置' in window.settings_editor.tab_names
        assert name in window.versions
        window.close();app.processEvents()
print('PASS: English pages, stable setting IDs, autosave, user text and Chinese restart')
