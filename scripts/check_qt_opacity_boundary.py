"""Exercise Qt's actual stylesheet parser at every transparency, especially 78/79%."""
import os,sys,re,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QWidget,QFrame
from PySide6.QtTest import QTest
from launcher.qtui.theme import appearance_style,_cached_appearance_base
from launcher.qtui.opacity import alpha_byte,opacity
from launcher.qtui.app import MainWindow
from launcher.config import Config
app=QApplication([]);app.setStyle('Fusion')
root=QWidget();root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);root.resize(100,100)
probe=QFrame(root);probe.setObjectName('settingRow');probe.setGeometry(10,10,80,80);root.show()
def capture():
    image=QImage(root.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);root.render(image)
    return image.pixelColor(40,40).alpha()
# Prove the exact failure and then test all outputs produced by our conversion.
probe.setStyleSheet('QFrame#settingRow {background:rgba(187,221,221,1);}')
QTest.qWait(5);assert capture()==255
_cached_appearance_base.cache_clear()
for mode in ('dark','light'):
    alpha=[]
    for value in range(91):
        css=appearance_style('#cebafa',{'color_mode':mode,'ui_transparency':value})
        declaration=re.search(r'QWidget#settingRow:hover\s*\{([^}]+)\}',css)[1]
        probe.setStyleSheet('QFrame#settingRow {'+declaration+'}');app.processEvents()
        actual=capture();expected=alpha_byte(7/255*opacity(value,90))
        assert actual==expected,(mode,value,actual,expected,declaration)
        alpha.append(actual)
    assert alpha==sorted(alpha,reverse=True)
    assert alpha[78:81]==[2,1,1]
assert _cached_appearance_base.cache_info().misses==2
assert _cached_appearance_base.cache_info().hits>=180
root.close()
# UI-only alpha changes must not reload/blur the wallpaper or reset font/layout geometry.
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='alpha-boundary-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    image=QImage(64,64,QImage.Format.Format_RGB32);image.fill(0xff2288bb)
    picture=base/'image.png';image.save(str(picture));config.set('background_image',str(picture))
    window=MainWindow(config.path,base);window.show();QTest.qWait(150)
    deadline=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<deadline:QTest.qWait(10)
    config=window.config_obj;config.set('background_scope','window');window.apply_appearance();app.processEvents()
    canvas=window.home_canvas;source_key=canvas.image.cacheKey()
    shell=window.centralWidget();shell.grab();wallpaper_key=shell._wallpaper_image.cacheKey()
    font=window.font().toString();geometry=window.geometry()
    for value in (77,78,79,80,85,90,78,0):
        config.set('ui_transparency',value);window.apply_appearance();shell.grab()
        assert canvas.image.cacheKey()==source_key
        assert shell._wallpaper_image.cacheKey()==wallpaper_key
        assert window.font().toString()==font and window.geometry()==geometry
    window.close()
print('PASS: reproduced byte-1 QSS ambiguity; 182 actual alpha measurements, 78/79% monotonic, cached style templates, unchanged wallpaper/font/geometry')
