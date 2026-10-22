"""Disposable offscreen checks for auto-save, instance scope and window chrome.

No desktop input, real account, network request or installed game is used.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtGui import QColor,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication,QDialog,QMessageBox,QInputDialog,
    QFileDialog,QColorDialog,QPushButton,QLabel,QVBoxLayout)
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.chrome import TitleBar
from launcher.qtui.widgets import configure_fonts

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app)
errors=[]
def exception_hook(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=exception_hook

def wait_for(predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate(),'Qt condition timed out'
    assert not errors,errors

def idle(window):wait_for(lambda:not window.tasks.jobs)

def screenshot(widget,name):
    app.processEvents()
    image=QImage(widget.size()*2,QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(2);image.fill(0);widget.render(image)
    destination=ROOT/'docs/screens'/name;destination.parent.mkdir(exist_ok=True)
    assert image.save(str(destination))

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-settings-') as directory:
    base=Path(directory);path=base/'onionmcl.json'
    config=Config(path);config.update({'game_dir':str(base/'minecraft'),
        'auto_memory':False,'min_memory':2048,'max_memory':4096})
    for vid in ('A-Fabric','B-Vanilla'):
        folder=base/'minecraft/versions'/vid;folder.mkdir(parents=True)
        (folder/(vid+'.json')).write_text(json.dumps({'id':vid,'mainClass':'Main','libraries':[]}),encoding='utf-8')
    window=MainWindow(path,base);window.error=lambda error:errors.append(str(error))
    window.show();wait_for(lambda:len(window.versions)==2);idle(window)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert isinstance(window.title_bar,TitleBar)
    # Controls act immediately; the title area delegates movement to Qt.
    controls=window._window_controls
    controls['maximize'].click();app.processEvents();assert window.isMaximized()
    assert controls['maximize'].toolTip()=='还原窗口'
    assert all(not grip.isVisible() for grip in window.frame_controller.handles)
    controls['maximize'].click();app.processEvents();assert not window.isMaximized()
    assert all(grip.isVisible() for grip in window.frame_controller.handles)
    with patch.object(window.frame_controller,'start_move',return_value=True) as move:
        QTest.mousePress(window.title_bar,Qt.MouseButton.LeftButton,pos=QPoint(226,20))
        QTest.mouseRelease(window.title_bar,Qt.MouseButton.LeftButton,pos=QPoint(226,20))
        assert move.call_count==1
    with patch.object(window.frame_controller,'start_resize',return_value=True) as resize:
        QTest.mouseClick(window.frame_controller.handles[0],Qt.MouseButton.LeftButton)
        assert resize.call_args.args[0]==Qt.Edge.TopEdge
    controls['minimize'].click();app.processEvents();assert window.isMinimized()
    window.showNormal();window.resize(1440,900)

    window.navigate('settings');global_editor=window.settings_editor
    assert not any(b.text()=='保存设置' for b in window.findChildren(QPushButton))
    assert not any(l.text()=='Java 管理' for l in global_editor.findChildren(QLabel))
    assert 'java' in window.nav and 'java_path' in global_editor.fields
    # Debounce saves without a navigation event or explicit save call.
    global_editor.fields['max_memory'].setValue(6144)
    wait_for(lambda:not global_editor.dirty)
    assert Config(path).get('max_memory')==6144
    # Invalid drafts do not overwrite the last valid file and stay editable.
    global_editor.fields['min_memory'].setValue(8192);QTest.qWait(550)
    assert global_editor.dirty and Config(path).get('min_memory')==2048
    assert '最小内存' in global_editor.hint.text()
    global_editor.fields['min_memory'].setValue(2048);wait_for(lambda:not global_editor.dirty)
    window.mutating=True;global_editor.fields['max_memory'].setValue(6400);QTest.qWait(550)
    assert global_editor.dirty and Config(path).get('max_memory')==6144
    window.mutating=False;wait_for(lambda:not global_editor.dirty)
    assert Config(path).get('max_memory')==6400

    # A gets a complete local snapshot; B remains on global defaults.
    window.set_selected('A-Fabric');window.instance_settings('A-Fabric');app.processEvents();a=window.instance_editor
    assert not a.specific.isChecked() and not a.stack.isEnabled()
    assert all(not field.isEnabled() for field in a.fields.values())
    assert all(not item.isEnabled() for item in a.stack.findChildren(QLabel))
    assert a.global_settings_button.isEnabled() and a.global_settings_button.isVisible()
    a.specific.setChecked(True);a.fields['max_memory'].setValue(8192)
    wait_for(lambda:not a.dirty)
    assert window.version_settings.resolve('A-Fabric',window.config_obj)['max_memory']==8192
    assert window.version_settings.get('B-Vanilla')=={}
    assert window.version_settings.resolve('B-Vanilla',window.config_obj)['max_memory']==6400
    window.set_selected('B-Vanilla');b=window.instance_editor
    assert not b.specific.isChecked() and not b.stack.isEnabled()
    b.global_settings_button.click()
    assert window.current_page=='settings' and global_editor.stack.currentIndex()==global_editor.tab_names['全局游戏设置']
    global_editor.fields['max_memory'].setValue(7168);wait_for(lambda:not global_editor.dirty)
    assert b.fields['max_memory'].value()==7168
    assert window.version_settings.resolve('A-Fabric',window.config_obj)['max_memory']==8192
    assert window.version_settings.resolve('B-Vanilla',window.config_obj)['max_memory']==7168
    window.navigate('instance');screenshot(window,'qt-inherited-settings.png')
    # The backend launch configuration reads the same per-instance resolver.
    assert window.version_settings.resolve('A-Fabric',window.config_obj)['width']==854
    window.set_selected('A-Fabric');a=window.instance_editor
    assert a.specific.isChecked() and a.fields['max_memory'].value()==8192
    a.specific.setChecked(False);wait_for(lambda:not a.dirty)
    assert a.fields['max_memory'].value()==7168 and not a.stack.isEnabled()
    assert window.version_settings.get('A-Fabric')=={}
    assert window.version_settings.get('B-Vanilla')=={}
    a.specific.setChecked(True);a.fields['max_memory'].setValue(8448)
    wait_for(lambda:not a.dirty)
    # Changing the selected global Java updates the cached editor as well.
    window.navigate('settings')
    with patch('launcher.java.find_all_java',return_value=[]):
        window.manage_java();idle(window)
    java_dialog=window.dialogs[-1]
    from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem
    tree=java_dialog.findChild(QTreeWidget);item=QTreeWidgetItem(['Java fixture','fixture-java.exe'])
    item.setData(0,Qt.ItemDataRole.UserRole,'fixture-java.exe');tree.addTopLevelItem(item);tree.setCurrentItem(item)
    next(b for b in java_dialog.findChildren(QPushButton) if b.text()=='使用所选').click()
    assert global_editor.fields['java_path'].text()=='fixture-java.exe'
    assert Config(path).get('java_path')=='fixture-java.exe'
    assert window.version_settings.resolve('A-Fabric',window.config_obj)['java_path']==''

    # Native Qt dialogs, confirmations and custom dialogs receive common chrome.
    dialogs=[QDialog(window),QMessageBox(QMessageBox.Icon.Information,'消息','示例内容',QMessageBox.StandardButton.Ok,window),
        QInputDialog(window),QFileDialog(window,'选择文件',str(base)),QColorDialog(QColor('#cebafa'),window)]
    dialogs[0].setWindowTitle('独立子窗口');QVBoxLayout(dialogs[0]).addWidget(QLabel('示例内容'))
    dialogs[2].setWindowTitle('输入名称');dialogs[2].setLabelText('名称');dialogs[2].setTextValue('Example')
    for dialog in dialogs:
        dialog.show();app.processEvents()
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint,type(dialog)
        assert dialog._chrome_header.isVisible() and dialog.styleSheet() and dialog.width()>=320,type(dialog)
        dialog.setWindowTitle('更新后的标题')
        assert dialog._chrome_header.findChild(QLabel).text()=='更新后的标题'
        assert dialog.layout().contentsMargins().top()>=46
        if isinstance(dialog,QMessageBox):screenshot(dialog,'qt-window-dialog.png')
        dialog._window_controls['close'].click();assert not dialog.isVisible()
        assert dialog.result()==QDialog.DialogCode.Rejected
    # Exec acceptance and standard button results survive layout decoration.
    modal=QMessageBox(QMessageBox.Icon.Question,'确认','确认测试',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,window)
    QTimer.singleShot(20,lambda:modal.button(QMessageBox.StandardButton.Yes).click())
    assert modal.exec()==QMessageBox.StandardButton.Yes
    QTimer.singleShot(20,lambda:app.activeModalWidget().accept())
    assert QInputDialog.getText(window,'名称','显示名称',text='Fixture')==('Fixture',True)
    reparented=QDialog(window);QVBoxLayout(reparented).addWidget(QLabel('嵌入测试'))
    reparented.show();app.processEvents()
    reserved=reparented.layout().contentsMargins().top()
    reparented.hide();reparented.setParent(window.stack,Qt.WindowType.Widget);app.processEvents()
    assert not reparented._chrome_header.isVisible()
    assert reparented.layout().contentsMargins().top()==reserved-46
    assert all(not grip.isVisible() for grip in reparented.frame_controller.handles)
    reparented.deleteLater()
    # Embedded pages have no second title bar; popups remain popups.
    window.open_accounts();embedded=window.subpages[-1]
    assert not embedded.isWindow()
    assert not getattr(embedded,'_chrome_header',None) or not embedded._chrome_header.isVisible()
    window.go_back();window.navigate('home');window.quick_select();picker=window.dialogs[-1]
    assert picker.windowType()==Qt.WindowType.Popup and not hasattr(picker,'_chrome_header')
    picker.reject()

    # Closing flushes a valid pending draft and restart restores selected instance.
    window.navigate('settings');global_editor.fields['window_width'].setValue(1280)
    assert global_editor.dirty
    window._window_controls['close'].click();app.processEvents()
    assert not window.isVisible() and Config(path).get('window_width')==1280
    restarted=MainWindow(path,base);restarted.show();wait_for(lambda:len(restarted.versions)==2);idle(restarted)
    assert restarted.selected_version=='A-Fabric'
    restarted.instance_settings('A-Fabric')
    assert restarted.instance_editor.specific.isChecked()
    assert restarted.instance_editor.fields['max_memory'].value()==8448
    restarted.set_selected('B-Vanilla')
    assert not restarted.instance_editor.specific.isChecked()
    assert not restarted.instance_editor.stack.isEnabled()
    assert restarted.instance_editor.fields['max_memory'].value()==7168
    restarted.close();app.processEvents()
    assert not errors,errors
print(json.dumps({'result':'pass','fixture_only':True,'desktop_input':False,
    'autosave_and_close_flush':True,'validation_and_busy_retry':True,
    'two_instance_isolation_and_restart':True,'inherited_fields_disabled':True,
    'single_java_management_entry':True,'frameless_main_and_dialogs':True,
    'dialog_results_preserved':True,'embedded_pages_and_popups':True}))
