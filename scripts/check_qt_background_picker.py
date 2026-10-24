"""Click the actual picture buttons; never opens a real system file dialog."""
import os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
app=QApplication([]);configure_fonts(app);errors=[]
def hook(kind,error,tb):errors.append(str(error));sys.__excepthook__(kind,error,tb)
sys.excepthook=hook
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='background-picker-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    image=QImage(120,80,QImage.Format.Format_RGB32);image.fill(QColor('#e56625'))
    path=base/'自定义 背景 [测试].png';assert image.save(str(path))
    window=MainWindow(config.path,base);window.show();QTest.qWait(150)
    end=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<end:QTest.qWait(10)
    window.navigate('settings');editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观'])
    choose=next(b for b in editor.findChildren(QPushButton) if b.text()=='选择图片')
    reset=next(b for b in editor.findChildren(QPushButton) if b.text()=='恢复默认')
    before={key:(field.text() if hasattr(field,'text') else None) for key,field in editor.fields.items()}
    with patch('launcher.qtui.settings.QFileDialog.getOpenFileName',return_value=(str(path),'图片')):choose.click()
    assert not errors,errors
    assert editor.fields['background_image'].text()==str(path),'Choose button changed the wrong field'
    assert editor.flush()
    assert Config(config.path).get('background_image')==str(path)
    assert window.home_canvas.original_image is not None and window.home_canvas.path==str(path)
    for key,value in before.items():
        if key!='background_image' and value is not None:assert editor.fields[key].text()==value,key
    with patch('launcher.qtui.settings.QFileDialog.getOpenFileName',return_value=('','')):choose.click()
    assert editor.fields['background_image'].text()==str(path)
    reset.click();assert not errors,errors
    assert editor.fields['background_image'].text()=='' and editor.flush()
    assert Config(config.path).get('background_image')=='' and window.home_canvas.image is None
    with patch('launcher.qtui.settings.QFileDialog.getOpenFileName',return_value=(str(path),'图片')):choose.click()
    assert editor.flush();window.navigate('home');QTest.qWait(30)
    assert window.home_canvas.path==str(path) and window.home_canvas.image is not None
    window.close();restored=MainWindow(config.path,base);restored.show();QTest.qWait(150)
    end=time.monotonic()+10
    while restored.tasks.jobs and time.monotonic()<end:QTest.qWait(10)
    assert restored.home_canvas.path==str(path) and restored.home_canvas.image is not None
    restored.close()
print('PASS: actual picture buttons, no unrelated field changes, cancel, restore, Unicode path, home and restart')
