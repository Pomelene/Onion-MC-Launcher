"""Custom welcome defaults, immediate preview and persistence; disposable data only."""
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.launch_control import LaunchControl

app=QApplication([]);configure_fonts(app);errors=[]
def report_exception(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=report_exception
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='welcome-') as directory:
    base=Path(directory);path=base/'onionmcl.json'
    config=Config(path);config.set('game_dir',str(base/'empty-game'))
    window=MainWindow(path,base);window.show();QTest.qWait(150)
    assert window.welcome_large.isHidden() and window.welcome_small.isHidden()
    assert not window.config_obj.get('custom_home_welcome')
    assert not any('自定义首页背景'==b.text() for b in window.findChildren(QPushButton))
    assert not window.account_button.subtitle
    window.navigate('settings');editor=window.settings_editor
    window.open_settings_tab(editor.tab_names['外观'])
    fields=editor.fields
    fields['custom_home_welcome'].setChecked(True)
    fields['home_welcome_large'].setText('<Onion & 大字>')
    fields['home_welcome_small'].setText('小字')
    assert window.welcome_large.text()=='<Onion & 大字>'
    assert window.welcome_small.text()=='小字'
    fields['custom_home_welcome'].setChecked(False)
    assert window.welcome_large.isHidden() and window.welcome_small.isHidden()
    assert not fields['home_welcome_large'].isEnabled()
    fields['custom_home_welcome'].setChecked(True)
    assert window.welcome_large.text()=='<Onion & 大字>'
    fields['custom_home_welcome'].setChecked(False)
    assert window.welcome_large.isHidden() and window.welcome_small.isHidden()
    window.navigate('home')
    assert window.welcome_large.isHidden() and window.welcome_small.isHidden()
    window.navigate('settings');fields['custom_home_welcome'].setChecked(True)
    assert editor.flush()
    window.close();QTest.qWait(50)
    restored=MainWindow(path,base);restored.show();QTest.qWait(150)
    assert restored.welcome_large.text()=='<Onion & 大字>'
    assert restored.welcome_small.text()=='小字'
    for mode in ('dark','light'):
        restored.config_obj.set('color_mode',mode);restored.apply_appearance()
        for width in (1100,1440):
            restored.resize(width,900);app.processEvents()
            restored.update_home_welcome({'custom_home_welcome':True,'home_welcome_large':'自定义主页标题','home_welcome_small':'自定义副标题'})
            app.processEvents()
            assert restored.welcome_large.width()<=restored.page_map['home'].width()
            destination=ROOT/'docs/screens'/f'qt-welcome-{mode}-{width}.png'
            destination.parent.mkdir(parents=True,exist_ok=True);assert restored.grab().save(str(destination))
    restored.status.setText('测试错误');assert not restored.status.isHidden()
    restored.status.setText('');assert restored.status.isHidden()
    restored.update_home_welcome({'custom_home_welcome':False})
    restored.launch_button.setText('启动游戏\n26.3-Fabric-THUnion');restored.quick_button.setEnabled(True)
    app.processEvents();assert restored.grab().save(str(ROOT/'docs/screens/qt-home-minimal.png'))
    # Verify independent click regions with callbacks that cannot launch a game.
    clicked=[];control=LaunchControl(lambda:clicked.append('launch'),lambda:clicked.append('select'))
    control.config_obj=restored.config_obj;control.launch.setText('启动游戏\n很长的实例名称'*4)
    control.show();app.processEvents();geometry=control.geometry()
    before=control.grab().toImage();assert before.pixelColor(299,10)==before.pixelColor(301,10)
    QTest.mousePress(control.launch,Qt.MouseButton.LeftButton);app.processEvents();assert control.geometry()==geometry
    QTest.mouseRelease(control.launch,Qt.MouseButton.LeftButton)
    QTest.mouseClick(control.quick,Qt.MouseButton.LeftButton);assert clicked==['launch','select']
    control.quick.setEnabled(False);app.processEvents()
    disabled=control.grab().toImage();assert disabled.pixelColor(325,10)==before.pixelColor(325,10)
    control.close()
    restored.close();QTest.qWait(50)
assert not errors,errors
print('PASS: default hidden, custom preview, disabled fields, content preservation, restart, literal text and 4 layouts')
