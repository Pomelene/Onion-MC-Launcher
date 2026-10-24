"""Shared popup, alignment, visible units, wide paths, bold and header fixtures."""
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QPushButton
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.choices import ChoiceComboBox,ActionMenu

app=QApplication([]);configure_fonts(app);errors=[]
def exception(kind,value,tb):errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=exception
def wait(predicate):
    end=time.monotonic()+8
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate() and not errors,errors
def capture(widget,name):
    app.processEvents();image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);widget.render(image)
    path=ROOT/'docs/screens'/name;path.parent.mkdir(parents=True,exist_ok=True);assert image.save(str(path));return image

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='ui-choices-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'empty-game'))
    window=MainWindow(config.path,base);window.show();wait(lambda:not window.tasks.jobs)
    assert window.brand_widget.parentWidget() is window.home_area and window.home_button.isHidden()
    capture(window,'qt-header-home-left.png')
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    assert window.brand_widget.parentWidget() is window.heading_area and not window.home_button.isHidden()
    for mode in ('dark','light'):
        editor.fields['color_mode'].setCurrentIndex(editor.fields['color_mode'].findData(mode));assert editor.flush()
        wait(lambda:not window.nav_motion.running)
        combo=editor.fields['color_mode'];assert isinstance(combo,ChoiceComboBox)
        activated=[];combo.activated.connect(activated.append)
        QTest.mouseClick(combo,Qt.MouseButton.LeftButton);app.processEvents();popup=combo.choice_popup
        assert popup is not None and popup.isVisible() and not hasattr(popup,'_chrome_header')
        image=capture(popup,f'qt-combo-{mode}.png');assert image.pixelColor(0,0).alpha()==0 and image.pixelColor(image.width()-1,image.height()-1).alpha()==0
        index=popup.proxy.index(combo.findData('light' if mode=='dark' else 'dark'),0);row=popup.proxy.mapToSource(index).row()
        QTest.mouseClick(popup.list.viewport(),Qt.MouseButton.LeftButton,pos=popup.list.visualRect(index).center())
        assert combo.currentIndex()==row and activated[-1]==row and not popup.isVisible();assert editor.flush()
        editor.fields['color_mode'].setCurrentIndex(editor.fields['color_mode'].findData(mode));assert editor.flush()
        editor.fields['bold_text'].setChecked(True);wait(lambda:editor.fields['background_scope'].font().weight()>=600)
        assert editor.fields['background_scope'].font().weight()>=600,(editor.fields['background_scope'].font().weight(),getattr(window.config_obj,'_qt_appearance_preview',None),window.styleSheet()[-200:])
        assert editor.flush() and Config(config.path).get('bold_text') is True
        editor.fields['bold_text'].setChecked(False);assert editor.flush()
        assert editor.fields['background_scope'].font().weight()<600
        for width in (1100,1440):
            window.resize(width,900);app.processEvents()
            field=editor.fields['background_image'];field.setText('C:/Pictures/自定义壁纸/landscapes/a-long-readable-wallpaper-name.png');assert editor.flush()
            editor.stack.currentWidget().ensureWidgetVisible(field);app.processEvents()
            assert field.width()>=360 and field.width()>field.parentWidget().width()/2
            for action in window.findChildren(QPushButton):
                if action.property('settingAction') and action.parentWidget().objectName()=='settingRow':
                    assert action.width()>=140 and action.geometry().right()<=action.parentWidget().width()-16
            capture(window,f'qt-path-{mode}-{width}.png')
        window.open_settings_tab(editor.tab_names['下载与网络']);wait(lambda:not window.nav_motion.running)
        limit=editor.fields['download_speed_limit'];assert limit.text()=='0' and not limit.suffix() and not limit.specialValueText()
        assert editor.unit_labels['download_speed_limit'].text()=='KiB/s' and editor.unit_labels['download_speed_limit'].isVisible()
        assert editor.number_hints['download_speed_limit'].text()=='不限速'
        limit.setValue(512);assert limit.text()=='512' and editor.number_hints['download_speed_limit'].text()=='';assert editor.flush()
        capture(window,f'qt-network-units-{mode}.png');limit.setValue(0);assert editor.flush()
        window.open_settings_tab(editor.tab_names['外观'])
    # Shared model mapping, filtering, disabled rows and keyboard commit.
    box=ChoiceComboBox(window);box.setGeometry(350,180,260,40)
    for i in range(24):box.addItem(f'选项 {i:02d}',i)
    box.model().item(3).setEnabled(False);box.show();box.showPopup();app.processEvents();popup=box.choice_popup
    assert popup.search.isVisible();popup.search.setText('选项 03');app.processEvents();popup.choose(popup.proxy.index(0,0));assert box.currentIndex()==0
    popup.search.setText('选项 17');app.processEvents();assert popup.proxy.rowCount()==1
    QTest.keyClick(popup.search,Qt.Key.Key_Down);QTest.keyClick(popup.list,Qt.Key.Key_Return)
    assert box.currentData()==17 and not popup.isVisible()
    box.showPopup();QTest.keyClick(popup.list,Qt.Key.Key_Escape);assert not popup.isVisible();box.hide()
    menu=ActionMenu(window);menu.addAction('打开实例目录');menu.addAction('重命名');menu.addSeparator();menu.addAction('移入恢复中心')
    menu.popup(QPoint(300,200));app.processEvents();image=capture(menu,'qt-action-menu.png');assert image.pixelColor(0,0).alpha()==0;menu.close()
    window.navigate('home');assert window.brand_widget.parentWidget() is window.home_area
    child=QDialog(window);child.setWindowTitle('子页面');window.show_subpage(child)
    assert window.brand_widget.parentWidget() is window.heading_area
    child.reject();assert window.brand_widget.parentWidget() is window.home_area
    window.close();app.processEvents()
    restored=MainWindow(config.path,base);assert restored.config_obj.get('bold_text') is False;restored.close();app.processEvents()
assert not errors,errors
print('PASS: shared rounded combos/menus, models/signals, disabled/filter/keyboard, aligned actions, wide paths at 1100/1440, external units, bold live/restart and route-aware branding')
