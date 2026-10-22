"""Offscreen appearance and wallpaper checks using disposable fixtures only."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QSize,QRectF,QRect,QPoint
from PySide6.QtGui import QImage,QColor,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QLineEdit,QSpinBox,QComboBox
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import HomeCanvas,ContentRow,background_rect,configure_fonts
from launcher.qtui.theme import paint_color,contrasting_accent

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def exception_hook(kind,value,tb):errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=exception_hook
def wait_for(predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate(),'Appearance check timed out'
    assert not errors,errors
def render(widget):
    app.processEvents();image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0);widget.render(image);assert not image.isNull();return image
def screenshot(window,name):
    wait_for(lambda:not window.nav_motion.running)
    path=ROOT/'docs/screens'/name;path.parent.mkdir(exist_ok=True);assert render(window).save(str(path))

expected={'fill':QRectF(-150,0,600,300),'fit':QRectF(0,75,300,150),
          'stretch':QRectF(0,0,300,300),'center':QRectF(50,100,200,100)}
for mode,rect in expected.items():assert background_rect(QSize(200,100),QSize(300,300),mode)==rect
for mode in ('dark','light'):
    assert QColor(contrasting_accent('#cebafa',mode)).isValid()
assert contrasting_accent('#cebafa','dark')=='#cebafa'
assert contrasting_accent('#cebafa','light')!='#cebafa'

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-appearance-') as folder:
    base=Path(folder);path=base/'onionmcl.json';config=Config(path)
    config.set('game_dir',str(base/'empty-library'))
    window=MainWindow(path,base);window.error=lambda error:errors.append(str(error));window.show()
    wait_for(lambda:not window.tasks.jobs);window.navigate('settings')
    editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观']);app.processEvents()
    assert editor.fields['color_mode'].currentData()=='dark'
    assert editor.fields['text_transparency'].value()==0
    position=editor.pos();original_stack=window.stack.currentWidget()
    def change(key,value):
        field=editor.fields[key]
        if hasattr(field,'findData'):field.setCurrentIndex(field.findData(value))
        elif hasattr(field,'setValue'):field.setValue(value)
        else:field.setText(value)
        wait_for(lambda:not editor.dirty)
        assert window.stack.currentWidget() is original_stack and window.settings_editor is editor
        assert editor.pos()==position
    screenshot(window,'qt-appearance-dark.png')
    change('color_mode','light')
    assert paint_color(window,'text').lightness()<80
    text=next(item for item in editor.findChildren(QLabel) if item.text()=='显示模式')
    assert text.palette().color(text.foregroundRole()).lightness()<80
    change('text_transparency',40)
    assert abs(paint_color(window,'text',text=True).alpha()-153)<=1
    assert abs(text.palette().color(text.foregroundRole()).alpha()-153)<=1
    change('ui_transparency',55)
    assert 'rgba(255,255,255,115)' in window.styleSheet()
    screenshot(window,'qt-appearance-light.png')
    for size in ((1100,740),(1440,900)):
        window.resize(*size);app.processEvents()
        assert all(field.width()>=(76 if key in editor.sliders else 100) for key,field in editor.fields.items() if field.isVisible() and isinstance(field,(QLineEdit,QSpinBox,QComboBox)))
        assert all(slider.width()>=150 for slider in editor.sliders.values() if slider.isVisible())
    change('text_transparency',0);change('ui_transparency',0)
    screenshot(window,'qt-appearance-light-default.png')
    # Custom painted content text and fallback icons adopt the same palette.
    row=ContentRow('示例模组','版本 1.0 · Fabric');row.setParent(window);row.resize(650,68)
    rendered=render(row)
    assert paint_color(row.text,'text').lightness()<80 and row._fallback_color is not None
    row.hide();row.setParent(None);row.deleteLater()
    # Small images keep their original dimensions for center/tile modes.
    image=QImage(32,16,QImage.Format.Format_RGB32);image.fill(QColor('#28a050'))
    painter=QPainter(image);painter.fillRect(16,0,16,16,QColor('#b04040'));painter.end()
    wallpaper=base/'wallpaper.png';assert image.save(str(wallpaper))
    change('background_image',str(wallpaper))
    window.navigate('home');app.processEvents();canvas=next(c for c in window.findChildren(HomeCanvas) if c.isVisible())
    assert canvas.image.size()==image.size()
    def render_wallpaper():
        root=window.centralWidget()
        return render(root).copy(QRect(canvas.mapTo(root,QPoint(0,0)),canvas.size()))
    visible=render_wallpaper()
    window.config_obj.set('background_transparency',100);window.apply_appearance()
    hidden=render_wallpaper()
    assert visible!=hidden and canvas.image.size()==image.size()
    window.config_obj.set('background_transparency',0);window.config_obj.set('background_mode','tile');window.apply_appearance()
    tiled=render_wallpaper()
    assert tiled.pixelColor(3,8)==tiled.pixelColor(35,8)
    assert tiled.pixelColor(3,8)!=tiled.pixelColor(19,8)
    screenshot(window,'qt-home-light-tile.png')
    # Normal preference changes use the editor and its automatic save path.
    window.navigate('settings');editor.fields['background_transparency'].setValue(65)
    wait_for(lambda:not editor.dirty)
    editor.fields['background_mode'].setCurrentIndex(editor.fields['background_mode'].findData('fit'))
    wait_for(lambda:not editor.dirty)
    saved=Config(path)
    assert saved.get('color_mode')=='light' and saved.get('background_mode')=='fit'
    assert saved.get('background_transparency')==65
    window.close();app.processEvents()
    restored=MainWindow(path,base);restored.show();wait_for(lambda:not restored.tasks.jobs)
    assert paint_color(restored,'text').lightness()<80
    restored.navigate('settings');restored.open_settings_tab(restored.settings_editor.tab_names['外观'])
    assert restored.settings_editor.fields['background_mode'].currentData()=='fit'
    assert restored.settings_editor.fields['background_transparency'].value()==65
    restored.close();app.processEvents()
    # Hand-edited out-of-range values are bounded on reload.
    saved.set('text_transparency',999);assert Config(path).get('text_transparency')==70
    saved.set('ui_transparency',-20);assert Config(path).get('ui_transparency')==0
    saved.set('background_mode','invalid');assert Config(path).get('background_mode')=='fill'
    assert not errors,errors
print(json.dumps({'result':'pass','fixture_only':True,'desktop_input':False,
    'dark_and_light':True,'independent_transparency':True,'background_modes':5,
    'original_image_size_preserved':True,'autosave_and_restart':True,'stable_page_identity':True}))
