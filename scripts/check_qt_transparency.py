"""Per-pixel transparent surfaces with independently opaque text; fixtures only."""
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
native='--native' in sys.argv
os.environ['QT_QPA_PLATFORM']='windows' if native else 'offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QVBoxLayout,QFileDialog
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts

app=QApplication([]);configure_fonts(app);errors=[]
def report_exception(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=report_exception
def wait(predicate):
    end=time.monotonic()+8
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate() and not errors,errors
def capture(widget):
    image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    widget.render(image);return image
def max_alpha(image,widget,owner):
    at=widget.mapTo(owner,QPoint(0,0))
    return max(image.pixelColor(x,y).alpha() for x in range(at.x(),at.x()+widget.width()) for y in range(at.y(),at.y()+widget.height()))

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='ui-alpha-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'empty-game'))
    window=MainWindow(config.path,base)
    if native:window.winId()
    else:window.show()
    wait(lambda:not window.tasks.jobs)
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    editor.fields['ui_transparency'].setValue(90);wait(lambda:not editor.dirty)
    assert window.windowOpacity()==1 and Config(config.path).get('ui_transparency')==90
    assert editor.sliders['ui_transparency'].value()==90
    assert window.title.palette().color(window.title.foregroundRole()).alpha()==255
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        for scope in ('content','window'):
            window.config_obj.set('background_scope',scope);window.apply_appearance();window.navigate('home');app.processEvents()
            image=capture(window)
            assert 20<=image.pixelColor(600,400).alpha()<=30,(mode,scope,image.pixelColor(600,400).alpha())
            assert max_alpha(image,window.brand_widget.findChildren(QLabel)[0],window)==255
            assert window.windowOpacity()==1
        # Show the same alpha image over a synthetic other-window background.
        if not native:
            backing=QImage(image.size(),QImage.Format.Format_RGB32);backing.fill(QColor('#2e8d94'))
            p=QPainter(backing)
            for y in range(0,backing.height(),100):
                for x in range(0,backing.width(),100):
                    if (x//100+y//100)%2:p.fillRect(x,y,100,100,QColor('#d9cb9d'))
            p.drawImage(0,0,image);p.end()
            destination=ROOT/'docs/screens'/f'qt-ui-alpha-{mode}.png';destination.parent.mkdir(parents=True,exist_ok=True);assert backing.save(str(destination))
    window.config_obj.set('text_transparency',70);window.apply_appearance()
    assert window.title.palette().color(window.title.foregroundRole()).alpha()==77
    window.config_obj.set('text_transparency',0);window.config_obj.set('ui_transparency',0);window.apply_appearance()
    assert capture(window).pixelColor(600,400).alpha()==255
    window.config_obj.set('ui_transparency',90);window.apply_appearance()
    dialog=QDialog(window);layout=QVBoxLayout(dialog);text=QLabel('独立窗口文字',dialog);layout.addWidget(text)
    if native:dialog.ensurePolished();app.processEvents();dialog.winId()
    else:dialog.show();app.processEvents()
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert dialog.windowOpacity()==1 and text.palette().color(text.foregroundRole()).alpha()==255
    chooser=QFileDialog(window);app.processEvents()
    assert not chooser.testOption(QFileDialog.Option.DontUseNativeDialog)
    chooser.close();dialog.close()
    if native:
        assert window.windowHandle().format().alphaBufferSize()>=8
        assert not any(w.isVisible() for w in app.topLevelWidgets())
    window.close();app.processEvents()
    config.set('ui_transparency',100);assert Config(config.path).get('ui_transparency')==90
assert not errors,errors
print('PASS: '+('hidden Windows native alpha surface; ' if native else '')+'90% surface transparency, opaque text, independent text opacity, both themes/scopes, reset, dialogs, native file pickers, autosave and bounds')
