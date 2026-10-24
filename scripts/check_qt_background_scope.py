"""Background scope integration with disposable images and preferences only."""
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QLinearGradient
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.theme import paint_color

app=QApplication([]);configure_fonts(app);errors=[]
def report_exception(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=report_exception
def wait(predicate):
    end=time.monotonic()+8
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate(),'Timed out'
    assert not errors,errors

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='background-scope-') as directory:
    base=Path(directory);path=base/'onionmcl.json';config=Config(path)
    assert config.get('background_scope')=='content'
    config.set('game_dir',str(base/'empty-game'))
    source=QImage(900,600,QImage.Format.Format_RGB32)
    painter=QPainter(source);gradient=QLinearGradient(0,0,900,600)
    gradient.setColorAt(0,QColor('#d94f70'));gradient.setColorAt(.5,QColor('#664fc9'));gradient.setColorAt(1,QColor('#27b9a5'))
    painter.fillRect(source.rect(),gradient);painter.end()
    image=base/'wallpaper.png';assert source.save(str(image));config.set('background_image',str(image))
    window=MainWindow(path,base);window.show();wait(lambda:not window.tasks.jobs)
    canvas=window.home_canvas;cache=canvas.image.cacheKey()
    assert not window.sidebar.property('wallpaperUnderlay')
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    page=window.stack.currentWidget();sidebar=window.sidebar
    scope=editor.fields['background_scope'];scope.setCurrentIndex(scope.findData('window'))
    wait(lambda:not editor.dirty)
    assert window.stack.currentWidget() is page and window.sidebar is sidebar
    assert window.sidebar.property('wallpaperUnderlay') and window.title_bar.property('wallpaperUnderlay')
    assert canvas.image.cacheKey()==cache
    assert Config(path).get('background_scope')=='window'
    window.navigate('home');app.processEvents();canvas=window.home_canvas
    # Both sides use one root image; the sidebar adds only its readability tint.
    window.config_obj.set('ui_transparency',0);window.apply_appearance()
    for mode in ('fill','fit','stretch','center','tile'):
        window.config_obj.set('background_mode',mode);window.apply_appearance();app.processEvents()
        actual=window.centralWidget().grab().toImage()
        expected=QImage(window.centralWidget().size(),QImage.Format.Format_ARGB32_Premultiplied)
        expected.fill(0);painter=QPainter(expected);canvas.paint_background(painter,expected.size())
        tint=paint_color(window,'base');tint.setAlpha(150)
        painter.fillRect(0,64,220,expected.height()-64,tint);painter.end()
        for x,y in ((218,500),(221,500),(100,min(820,actual.height()-50)),(350,500)):
            assert actual.pixelColor(x,y)==expected.pixelColor(x,y),(mode,x,y,actual.pixelColor(x,y).name(),expected.pixelColor(x,y).name())
    window.config_obj.set('ui_transparency',0);window.config_obj.set('background_mode','fill');window.apply_appearance()
    for color_mode in ('dark','light'):
        window.config_obj.set('color_mode',color_mode);window.apply_appearance()
        for scope_value in ('window','content'):
            window.config_obj.set('background_scope',scope_value);window.apply_appearance();app.processEvents()
            output=ROOT/'docs/screens'/f'qt-background-{color_mode}-{scope_value}.png'
            output.parent.mkdir(parents=True,exist_ok=True);assert window.grab().save(str(output))
    # Switching back restores ordinary surfaces; hiding the image does not remove controls.
    assert not window.sidebar.property('wallpaperUnderlay')
    window.config_obj.set('background_scope','window');window.config_obj.set('background_transparency',100);window.apply_appearance()
    hidden=window.centralWidget().grab().toImage()
    window.config_obj.set('background_transparency',0);window.apply_appearance()
    assert hidden!=window.centralWidget().grab().toImage()
    assert window.launch_button.isVisible() and window.account_button.isVisible()
    window.close();app.processEvents()
    restored=MainWindow(path,base);restored.show();wait(lambda:not restored.tasks.jobs)
    assert restored.config_obj.get('background_scope')=='window'
    assert restored.sidebar.property('wallpaperUnderlay')
    restored.close();app.processEvents()
    config.set('background_scope','invalid');assert Config(path).get('background_scope')=='content'
assert not errors,errors
print('PASS: both scopes, shared coordinates in 5 image modes, no duplicate decoding on toggle, stable settings page, opacity, dark/light, restart and invalid value')
