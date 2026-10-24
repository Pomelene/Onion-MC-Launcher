"""Offscreen screen-size and persisted geometry checks; no personal data."""
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QMainWindow
from launcher.config import Config
from launcher.qtui.window_size import fitted_size, restore_window_size, remember_window_size
app=QApplication([])
for width,height in ((1920,1040),(1536,824),(1366,728),(1024,720),(800,560),(3840,2120)):
    minimum,size=fitted_size(QSize(width,height))
    assert size.width()<=width and size.height()<=height
    assert size.width()<=1280 and size.height()<=800
    _,saved=fitted_size(QSize(width,height),5000,4000)
    assert saved.width()<=width and saved.height()<=height
assert fitted_size(QSize(1920,1040),1040,680)[1]==QSize(1040,680)
assert fitted_size(QSize(1536,824))[1]==QSize(1260,676)
with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
    path=Path(folder)/'settings.json';config=Config(path)
    window=QMainWindow();restore_window_size(window,config);window.show();app.processEvents()
    window.resize(950,650);app.processEvents();expected=window.size();remember_window_size(window,config)
    stored=Config(path)
    assert stored.get('launcher_window_width')==expected.width() and stored.get('launcher_window_height')==expected.height()
    assert stored.get('window_width')==854 and stored.get('window_height')==480
    window.showMaximized();app.processEvents();remember_window_size(window,config)
    assert config.get('launcher_window_maximized')
    assert config.get('launcher_window_width')==expected.width()
    window.close()
    restored=QMainWindow();restore_window_size(restored,Config(path))
    assert restored.windowState() & Qt.WindowState.WindowMaximized
    restored.close()
from launcher.qtui.app import MainWindow
with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
    base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    window=MainWindow(config.path,base);window.show()
    import time
    until=time.monotonic()+15
    while window.tasks.jobs and time.monotonic()<until:
        app.processEvents();time.sleep(.01)
    app.processEvents()
    area=window.screen().availableGeometry()
    assert window.width()<=area.width() and window.height()<=area.height(), (window.size(),area)
    window.resize(960,660);app.processEvents();expected=window.size();assert window.close()
    saved=Config(config.path)
    assert saved.get('launcher_window_width')==expected.width() and saved.get('launcher_window_height')==expected.height()
print('PASS: first-run screen fitting, DPI logical sizes, saved sizes, smaller screens, maximized restore, separate game settings')
