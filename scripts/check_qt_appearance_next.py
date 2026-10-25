"""New appearance controls and pixel/layout behavior, isolated and offscreen."""
import sys,os,tempfile,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QImage,QColor,QPainter,QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import ContentRow,configure_fonts
from launcher.qtui.theme import APPEARANCE_KEYS,effective_accent,corner,resolved_mode
from launcher.qtui.color_science import image_seed,contrast,palette,_wallpaper_seed
app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def hook(kind,error,tb):
    errors.append(str(error));sys.__excepthook__(kind,error,tb)
sys.excepthook=hook
def wait(predicate):
    deadline=time.monotonic()+15
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate() and not errors,errors
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='appearance-next-') as folder:
    base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    source=QImage(640,400,QImage.Format.Format_RGB32);source.fill(QColor('#4477bb'))
    p=QPainter(source)
    for x in range(0,640,8):p.fillRect(x,0,4,400,QColor('#4e81bf'))
    p.fillRect(0,0,80,400,QColor('#111111'));p.end()
    path=base/'test.png';source.save(str(path));config.set('background_image',str(path))
    assert image_seed(source)!='#cebafa'
    window=MainWindow(config.path,base);window.show();QTest.qWait(150);wait(lambda:not window.tasks.jobs)
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    assert APPEARANCE_KEYS<=editor.fields.keys()
    def change(key,value):
        f=editor.fields[key]
        if hasattr(f,'findData'):f.setCurrentIndex(f.findData(value))
        elif hasattr(f,'setChecked'):f.setChecked(value)
        elif hasattr(f,'setValue'):f.setValue(value)
        else:f.setText(value)
        wait(lambda:not editor.dirty);QTest.qWait(40)
        assert window.settings_editor is editor
    change('accent_source','wallpaper');assert effective_accent(window.config_obj)!='#cebafa'
    for mode in ('light','dark'):
        change('color_mode',mode)
        for style in ('fidelity','tonal_spot','vibrant','neutral','fruit_salad','rainbow'):
            change('color_style',style)
            image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);window.render(image)
    change('color_mode','auto')
    from unittest.mock import patch
    # Offscreen QPA has no OS preferences; simulate the documented Qt signal contract.
    for mode,scheme in (('light',Qt.ColorScheme.Light),('dark',Qt.ColorScheme.Dark)):
        with patch('launcher.qtui.theme.system_color_mode',return_value=mode):
            app.styleHints().colorSchemeChanged.emit(scheme);QTest.qWait(50)
            assert resolved_mode(window.config_obj)==mode
            assert ('background:rgb(' in window.styleSheet()) or window.styleSheet()
    change('color_mode','dark')
    change('titlebar_transparent',False);change('ui_transparency',90)
    assert 'QWidget#toolbar[wallpaperUnderlay="true"] { background:#ff' in window.styleSheet()
    change('corner_radius',0);assert corner(window)==0
    change('corner_radius',20);assert corner(window)==20
    row=ContentRow('测试列表标题 · Unicode','副标题和版本信息');row.setParent(window)
    change('font_size',18);assert window.font().pixelSize()==18
    change('log_font_size',20);assert '20px' in window.logs.styleSheet()
    change('font_antialiasing','gray');assert window.font().styleStrategy() & QFont.StyleStrategy.NoSubpixelAntialias
    change('animation_duration',500)
    button=window.home_button;button._start(button.press_animation,0,1)
    assert button.press_animation.duration()==375
    change('animation_duration',0);button._start(button.press_animation,0,1);assert button.press_amount==1
    canvas=window.home_canvas;original=canvas.original_image.copy()
    change('background_blur',16)
    assert canvas.original_image==original and canvas.image!=original and canvas.image.size()==original.size()
    # A uniform opaque fixture keeps an opaque center/edge after filtering.
    assert canvas.image.pixelColor(320,200).alpha()==255
    cached=canvas.image.cacheKey();window.apply_appearance();assert canvas.image.cacheKey()==cached
    change('background_blur',0);assert canvas.image==original
    editor.reset_appearance();wait(lambda:not editor.dirty)
    assert window.config_obj.get('font_size')==14 and window.config_obj.get('corner_radius')==10
    change('color_mode','light');change('color_style','tonal_spot')
    window.resize(1200,840);QTest.qWait(50)
    folder=ROOT/'docs/screens';folder.mkdir(exist_ok=True)
    image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);window.render(image);image.save(str(folder/'qt-appearance-next.png'))
    assert window.close()
    restored=Config(config.path);assert restored.get('color_style')=='tonal_spot'
assert not errors,errors
print('PASS: all controls, 12 palettes, wallpaper seed, OS mode changes, fonts, corner, blur cache, durations, reset and persistence')
