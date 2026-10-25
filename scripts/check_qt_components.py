"""Exercise the real existing-instance UI and replacement backend offline."""
import os,sys,time,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.component_versions import ComponentVersions
from launcher.qtui.installer import InstallDialog
from launcher.components import component_info
from tests.test_components import fixture,data_snapshot
app=QApplication([]);configure_fonts(app);errors=[]
def exception(kind,value,trace):errors.append(str(value));sys.__excepthook__(kind,value,trace)
sys.excepthook=exception
def idle(window):
    end=time.monotonic()+15;app.processEvents()
    while window.tasks.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not window.tasks.jobs,'Component task timed out'
    assert not errors,errors
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='components-ui-') as tmp:
    base=Path(tmp);repo,vid=fixture(base);window=MainWindow(repo.config.path,base);window.show();idle(window)
    window.repo.downloader.fetch_json=repo.downloader.fetch_json
    window.instances.update(vid,name='My custom instance',favorite=True,tags=['keep'])
    window.set_selected(vid);meta=window.instances.get(vid);before=data_snapshot(window.repo,vid);ids=window.repo.list_installed()
    window.navigate('instance');window.open_instance_tab('auto');idle(window)
    controls=window.instance_workspace.pages['auto'].findChildren(QPushButton)
    assert not any(b.text()=='安装 / 更换加载器' for b in controls)
    next(b for b in controls if b.text()=='更换版本').click();idle(window)
    selector=window.subpages[-1];assert isinstance(selector,ComponentVersions) and not selector.isWindow()
    assert selector.game=='26.3' and selector.vid==vid
    assert selector.install_button.text()=='已安装' and not selector.install_button.isEnabled()
    assert not any(isinstance(p,InstallDialog) for p in window.subpages)
    selector.tree.setCurrentItem(selector.tree.topLevelItem(0));assert selector.install_button.isEnabled()
    with patch.object(window.repo,'_ensure_libraries'),patch.object(window.repo,'install',side_effect=AssertionError('Must not create an instance')):
        selector.install_button.click();idle(window)
    assert component_info(window.repo,vid)==('26.3','fabric','0.19.5')
    assert window.selected_version==vid and window.repo.list_installed()==ids
    assert data_snapshot(window.repo,vid)==before and window.instances.get(vid)==meta
    assert not any(isinstance(p,InstallDialog) for p in window.subpages)
    window.resize(900,600);QTest.qWait(30);window.grab().save(str(ROOT/'tmp/component-updated.png'))
    next(b for b in window.instance_workspace.pages['auto'].findChildren(QPushButton) if b.text()=='更换版本').click();idle(window)
    selector=window.subpages[-1];assert selector.install_button.text()=='已安装' and not selector.install_button.isEnabled()
    selector.reject();window.close()
assert not errors,errors
print('PASS: inline component selector, actual Minecraft version, current-version state, real in-place Fabric update, stable instance ID, metadata and game files preserved, no new-install page')
