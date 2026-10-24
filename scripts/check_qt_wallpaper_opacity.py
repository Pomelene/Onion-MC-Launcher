"""Independent wallpaper/UI opacity, actual backdrop rendering; disposable data."""
import os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QImage,QColor,QPainter,QRegion
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
app=QApplication([]);app.setStyle('Fusion')
def capture(widget):
    app.processEvents()
    image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    widget.render(image,QPoint(),QRegion(),QWidget.RenderFlag(0))
    return image
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='wallpaper-opacity-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'empty-game'))
    fixture=QImage(320,200,QImage.Format.Format_RGB32);fixture.fill(QColor('#f05b97'))
    path=base/'wallpaper.png';assert fixture.save(str(path));config.set('background_image',str(path))
    window=MainWindow(config.path,base);window.show();QTest.qWait(100)
    deadline=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not window.tasks.jobs
    QTest.qWait(50)
    config=window.config_obj;window.apply_appearance()
    shell=window.centralWidget();canvas=window.home_canvas
    for theme in ('dark','light'):
        for scope in ('content','window'):
            for mode in ('fill','fit','stretch','center','tile'):
                config.update({'color_mode':theme,'background_scope':scope,'background_mode':mode,'background_transparency':0,'ui_transparency':0})
                window.apply_appearance();opaque=capture(shell)
                point=canvas.mapTo(shell,canvas.rect().center()) if scope=='content' else shell.rect().center()
                expected=opaque.pixelColor(point)
                wallpaper=shell._wallpaper_image.copy()
                assert expected.alpha()==255
                for value in (5,50,90):
                    config.set('ui_transparency',value);window.apply_appearance();image=capture(shell)
                    assert image.pixelColor(point)==expected,(theme,scope,mode,value,image.pixelColor(point).getRgb(),expected.getRgb(),point)
                if scope=='content':assert abs(image.pixelColor(10,10).alpha()-26)<=2,(theme,scope,mode,image.pixelColor(10,10).getRgb())
                elif mode in ('fill','stretch','tile'):assert image==opaque
                assert shell._wallpaper_image==wallpaper
                # UI at 90% transparency and wallpaper at 50% combine as .1 + .5*.9.
                config.set('background_transparency',50);window.apply_appearance();image=capture(shell)
                assert abs(image.pixelColor(point).alpha()-round(255*.55))<=2
                config.set('background_transparency',100);window.apply_appearance();image=capture(shell)
                assert abs(image.pixelColor(point).alpha()-26)<=2
                assert window.title.palette().color(window.title.foregroundRole()).alpha()==255
                assert window.windowOpacity()==1
    # Live slider preview has the same independent layer behavior as saved settings.
    config.update({'background_scope':'window','background_transparency':0,'ui_transparency':0})
    window.apply_appearance();before=capture(shell)
    config._qt_appearance_preview={'ui_transparency':90}
    window.apply_appearance();assert capture(shell)==before
    del config._qt_appearance_preview
    window.navigate('settings');config.update({'background_scope':'content','ui_transparency':90})
    window.apply_appearance();assert abs(capture(shell).pixelColor(10,10).alpha()-26)<=2
    # Cache reuse during shrinking must not leave old wallpaper pixels outside its scope.
    for size in ((1280,800),(1000,680),(900,600)):
        window.resize(*size);window.navigate('home');app.processEvents()
        image=capture(shell);assert image.size()==shell.size()
        assert abs(image.pixelColor(10,10).alpha()-26)<=2
    window.close();app.processEvents()
print('PASS: independent wallpaper opacity, 5 modes, both themes/scopes, live preview, text, navigation and resize')
