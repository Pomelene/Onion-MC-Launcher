"""Disposable picker interaction and rendered-layout checks, without desktop input."""
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication,QDialog,QPushButton
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.color_picker import ColorPicker
from launcher.qtui.widgets import configure_fonts

app=QApplication([]);configure_fonts(app);errors=[]
def exception(kind,value,tb):errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=exception

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='picker-') as directory:
    root=Path(directory);config=Config(root/'onionmcl.json');config.set('game_dir',str(root/'empty-game'))
    window=MainWindow(config.path,root)
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        picker=ColorPicker('#cebafa',editor);picker.show();app.processEvents()
        assert picker.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert picker.hex.text()=='#cebafa' and tuple(f.value() for f in picker.rgb)==(206,186,250)
        assert picker.width()==540 and picker.height()<600,(picker.size(),picker.sizeHint())
        assert picker.plane.geometry().top()>=46
        assert picker.confirm.geometry().bottom()<=picker.height()-16
        QTest.mouseClick(picker.swatches[3],Qt.MouseButton.LeftButton);assert picker.color.name()=='#60a5fa'
        QTest.mouseClick(picker.original_swatch,Qt.MouseButton.LeftButton);assert picker.color.name()=='#cebafa'
        picker.hex.setFocus();picker.hex.selectAll();QTest.keyClicks(picker.hex,'xyz');assert not picker.confirm.isEnabled()
        picker.accept();assert picker.isVisible() and picker.error.text()
        picker.hex.selectAll();QTest.keyClicks(picker.hex,'336699');assert picker.color.name()=='#336699'
        QTest.keyClick(picker.hex,Qt.Key.Key_Tab);assert picker.hex.text()=='#336699'
        picker.rgb[0].setValue(255);assert picker.hex.text()=='#ff6699'
        area=picker.plane.area();QTest.mouseClick(picker.plane,Qt.MouseButton.LeftButton,pos=QPoint(round(area.right()),round(area.top())))
        assert picker.color.hsvSaturationF()>.99 and picker.color.valueF()>.99
        QTest.keyClick(picker.plane,Qt.Key.Key_Left);assert .97<picker.color.hsvSaturationF()<1
        QTest.mouseClick(picker.hue_slider,Qt.MouseButton.LeftButton,pos=QPoint(picker.hue_slider.width()//2,14))
        assert 177<=picker.hue<=181
        QTest.keyClick(picker.hue_slider,Qt.Key.Key_Left);assert picker.hue_slider.value()<181
        picker.set_color(QColor('black'));picker.hue_slider.setValue(280);picker.plane.value=.8
        picker.sv_changed(.5,.8);assert picker.color.hsvHue()==280
        picker.set_color(QColor('#cebafa'));app.processEvents()
        image=QImage(picker.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);picker.render(image)
        path=ROOT/'docs/screens'/f'qt-color-picker-{mode}.png';path.parent.mkdir(parents=True,exist_ok=True);assert image.save(str(path))
        picker.reject();assert editor.fields['accent_color'].text()=='#cebafa'
    # Exercise the real settings callback, including modal acceptance/cancellation.
    control=next(b for b in editor.findChildren(QPushButton) if b.text()=='选择颜色')
    def finish(accept):
        picker=app.activeModalWidget();assert isinstance(picker,ColorPicker)
        picker.set_color(QColor('#34d399'));picker.accept() if accept else picker.reject()
    QTimer.singleShot(20,lambda:finish(False));control.click();assert editor.fields['accent_color'].text()=='#cebafa'
    QTimer.singleShot(20,lambda:finish(True));control.click();assert editor.fields['accent_color'].text()=='#34d399'
    assert editor.flush() and Config(config.path).get('accent_color')=='#34d399'
    window.close();app.processEvents()
assert not errors,errors
print('PASS: HSV drag/keyboard, HEX/RGB sync/validation, achromatic hue, presets/original reset, confirm/cancel persistence, dark/light frameless layout, fixture only')
