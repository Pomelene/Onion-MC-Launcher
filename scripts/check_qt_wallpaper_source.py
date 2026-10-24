"""Actual source popup clicks at large font/density; wallpaper/custom round trips."""
import os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.theme import effective_accent
app=QApplication([]);configure_fonts(app)
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='wallpaper-source-') as folder:
    base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    picture=QImage(96,64,QImage.Format.Format_RGB32);picture.fill(QColor('#22a755'))
    path=base/'green.png';picture.save(str(path));config.set('background_image',str(path))
    window=MainWindow(config.path,base);window.show();QTest.qWait(150)
    end=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<end:QTest.qWait(10)
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    page=editor.stack.currentWidget();source=editor.fields['accent_source']
    editor.fields['accent_color'].setText('#ae45d2');assert editor.flush()
    custom=effective_accent(window.config_obj)
    for size in (14,18):
        for density in ('compact','standard','comfortable'):
            editor.fields['font_size'].setValue(size);editor.fields['list_density'].setCurrentIndex(editor.fields['list_density'].findData(density));assert editor.flush()
            page.ensureWidgetVisible(source,20,100);QTest.qWait(50)
            for value in ('wallpaper','custom','wallpaper','custom'):
                source.showPopup();app.processEvents();popup=source.choice_popup
                for index in range(source.count()):
                    rect=popup.list.visualRect(popup.proxy.index(index,0))
                    assert popup.list.viewport().rect().contains(rect),(size,density,index,rect,popup.list.viewport().rect())
                target=popup.proxy.index(source.findData(value),0)
                QTest.mouseClick(popup.list.viewport(),Qt.MouseButton.LeftButton,pos=popup.list.visualRect(target).center())
                assert source.currentData()==value and not popup.isVisible()
                assert editor.flush();QTest.qWait(40)
                assert Config(window.config_obj.path).get('accent_source')==value
                assert editor.fields['accent_color'].text()=='#ae45d2'
                if value=='wallpaper':assert effective_accent(window.config_obj)!=custom
                else:assert effective_accent(window.config_obj)==custom
    source.setCurrentIndex(source.findData('wallpaper'));assert editor.flush()
    assert not editor.fields['accent_color'].isEnabled()
    assert '壁纸取色' in editor.palette_feedback.text()
    assert window.config_obj._qt_wallpaper_seed in editor.palette_feedback.text()
    previous=effective_accent(window.config_obj)
    blue=QImage(96,64,QImage.Format.Format_RGB32);blue.fill(QColor('#3069ce'))
    blue_path=base/'blue.png';blue.save(str(blue_path));editor.fields['background_image'].setText(str(blue_path));assert editor.flush()
    assert effective_accent(window.config_obj)!=previous
    assert window.config_obj._qt_wallpaper_seed in editor.palette_feedback.text()
    from unittest.mock import patch
    from launcher.qtui.color_picker import ColorPicker
    def accept_color(picker):
        picker.color=QColor('#e36827');return QDialog.DialogCode.Accepted
    with patch.object(ColorPicker,'exec',accept_color):editor.choose_accent_button.click()
    assert editor.flush() and source.currentData()=='custom'
    assert editor.fields['accent_color'].isEnabled() and editor.fields['accent_color'].text()=='#e36827'
    source.setCurrentIndex(source.findData('wallpaper'));assert editor.flush()
    gray=QImage(64,64,QImage.Format.Format_RGB32);gray.fill(QColor('#808080'))
    gray_path=base/'gray.png';gray.save(str(gray_path));editor.fields['background_image'].setText(str(gray_path));assert editor.flush()
    assert '默认紫色' in editor.palette_feedback.text() and not window.config_obj._qt_wallpaper_seed_found
    editor.fields['background_image'].setText(str(base/'missing.png'));assert editor.flush()
    assert '默认紫色' in editor.palette_feedback.text()
    source.setCurrentIndex(source.findData('custom'));assert editor.flush()
    assert editor.fields['accent_color'].text()=='#e36827' and '自定义' in editor.palette_feedback.text()
    window.close()
print('PASS: both options fully visible, 24 mouse-click round trips, all densities, large font, stored manual color and wallpaper palette')
