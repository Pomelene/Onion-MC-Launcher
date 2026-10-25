"""Exercise accidental scrolling and catalog refresh without network or user data."""
import os,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QVBoxLayout,QPushButton
from PySide6.QtTest import QTest
from launcher.qtui.choices import ChoiceComboBox
from launcher.qtui.widgets import InlineSpinBox,configure_fonts
from launcher.qtui.settings import SettingsSlider
from launcher.qtui.project_versions import ProjectVersions
app=QApplication([]);configure_fonts(app);errors=[]
def report(kind,value,tb):
    errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=report


host=QWidget();layout=QVBoxLayout(host);other=QLineEdit();layout.addWidget(other)
combo=ChoiceComboBox();combo.addItems(['A','B','C']);combo.setCurrentIndex(1)
spin=InlineSpinBox();spin.setRange(0,100);spin.setValue(50)
slider=SettingsSlider(Qt.Orientation.Horizontal);slider.setRange(0,100);slider.setValue(50)
for control in (combo,spin,slider):layout.addWidget(control)
host.show();app.processEvents()
for control in (combo,spin,slider):
    other.setFocus();app.processEvents();assert not control.hasFocus()
    before=control.currentIndex() if control is combo else control.value()
    wheel=QWheelEvent(QPointF(control.rect().center()),QPointF(control.mapToGlobal(control.rect().center())),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    app.sendEvent(control,wheel)
    assert (control.currentIndex() if control is combo else control.value())==before
    assert not wheel.isAccepted(),'Unfocused editor must leave wheel scrolling to its parent'
    control.setFocus();QTest.keyClick(control,Qt.Key.Key_Down if control is combo else Qt.Key.Key_Up)
    assert (control.currentIndex() if control is combo else control.value())!=before,'Keyboard editing must still work'
host.close()

class PendingTasks:
    def submit(self,work,done,failed):self.done=done;self.failed=failed
class Window(QWidget):
    def __init__(self):
        super().__init__();self.tasks=PendingTasks();self.repo=SimpleNamespace(downloader=None)
        self.instances=SimpleNamespace(display_name=lambda vid:'测试实例');self.installs=[]
    def install_project(self,*args,**kwargs):self.installs.append((args,kwargs));return False
window=Window();dialog=ProjectVersions(window,'example','测试模组','mod','1.21.1','fabric','fixture')
dialog.show();QTest.qWait(20);assert dialog.loading and not dialog.install_button.isEnabled()
def release(key,game='1.21.1',files=True):
    return dict(id=key,version_number=key,game_versions=[game],loaders=['fabric'],version_type='release',date_published='2026-10-25',files=[dict(filename=key+'.jar',primary=True)] if files else [])
entries=[release('new'),release('chosen'),release('wrong','1.20.1'),release('empty',files=False)]
window.tasks.done(entries);assert not dialog.loading and dialog.refresh_button.isEnabled()
dialog.tree.setCurrentItem(dialog.tree.topLevelItem(1));assert dialog.install_button.isEnabled()
QTest.mouseClick(dialog.refresh_button,Qt.MouseButton.LeftButton)
assert dialog.loading and not dialog.install_button.isEnabled() and not dialog.refresh_button.isEnabled()
dialog.install();assert not window.installs
window.tasks.done([release('newest')]+entries)
assert dialog.tree.currentItem().data(0,Qt.ItemDataRole.UserRole)=='chosen'
assert dialog.install_button.isEnabled()
dialog.compatible.setChecked(False)
assert dialog.tree.currentItem().data(0,Qt.ItemDataRole.UserRole)=='chosen'
for i in range(dialog.tree.topLevelItemCount()):
    item=dialog.tree.topLevelItem(i)
    assert item.toolTip(4)==item.text(4)
    if item.data(0,Qt.ItemDataRole.UserRole) in ('wrong','empty'):
        dialog.tree.setCurrentItem(item);assert not dialog.install_button.isEnabled()
        dialog.install();assert not window.installs
dialog.tree.setCurrentItem(dialog.tree.topLevelItem(2));dialog.fetch();window.tasks.failed(RuntimeError('fixture'))
assert not dialog.loading and dialog.refresh_button.isEnabled() and dialog.install_button.isEnabled()
assert '重试' in dialog.status.text()
QTest.mouseClick(dialog.install_button,Qt.MouseButton.LeftButton)
assert window.installs[-1][1]['release_id']=='chosen'
dialog.fetch();dialog.reject();window.tasks.done(entries);assert not dialog.active
window.close()

from launcher.config import Config
from launcher.qtui.app import MainWindow
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='usability-') as directory:
    base=Path(directory);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    main=MainWindow(config.path,base);main.show();QTest.qWait(100)
    deadline=time.monotonic()+10
    while main.tasks.jobs and time.monotonic()<deadline:QTest.qWait(10)
    main.navigate('versions');app.processEvents();page=main.page_map['versions']
    buttons={b.text():b for b in page.findChildren(QPushButton)}
    assert not buttons['管理'].isEnabled() and not buttons['使用此实例'].isEnabled() and not buttons['新建'].isEnabled()
    assert buttons['安装'].isEnabled() and buttons['导入'].isEnabled()
    assert main.library_search.isClearButtonEnabled()
    main.versions=['fixture-A','fixture-B'];main.kinds={v:'原版' for v in main.versions};main.selected_version='fixture-A'
    main.build_versions();app.processEvents();buttons={b.text():b for b in page.findChildren(QPushButton) if b.isVisible()}
    # Old page widgets are deleted asynchronously, so use the current tree layout.
    assert main.version_tree.topLevelItemCount()==2
    for i in range(2):
        item=main.version_tree.topLevelItem(i)
        assert item.toolTip(1)==item.text(1)
    assert buttons['管理'].isEnabled() and buttons['使用此实例'].isEnabled()
    main.library_search.setText('no-such-instance');app.processEvents()
    assert not buttons['管理'].isEnabled() and not buttons['使用此实例'].isEnabled()
    main.library_search.clear();app.processEvents()
    assert buttons['管理'].isEnabled() and buttons['使用此实例'].isEnabled()
    main.close()
assert not errors,errors
print('PASS: scroll protection, keyboard input, catalog selection/refresh/failure/close, compatibility guards, empty-library actions')
