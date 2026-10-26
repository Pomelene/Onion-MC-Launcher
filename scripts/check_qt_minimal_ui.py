"""Isolated task-list painting and refresh regression checks."""
import os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.task_center import TaskCenter
from launcher.qtui.widgets import configure_fonts
app=QApplication([]);configure_fonts(app)
errors=[]
def error_hook(kind,value,trace):
    errors.append(str(value));sys.__excepthook__(kind,value,trace)
sys.excepthook=error_hook
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='minimal-ui-') as tmp:
    root=Path(tmp);config=Config(root/'onionmcl.json');config.set('game_dir',str(root/'game'))
    window=MainWindow(config.path,root);window.show()
    end=time.monotonic()+15
    while window.tasks.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not window.tasks.jobs
    history=window.task_history
    for i in range(40):
        item=history.begin('安装 Fabric '+str(i),'fixture/game','26.3')
        item['bytes']=600000+i;history.finish(item,'complete')
    window.choose_download_kind('tasks');page=window.download_tasks
    for mode in ('dark','light'):
        window.config_obj.update({'color_mode':mode,'font_size':14,'bold_text':True});window.apply_appearance()
        window.resize(1100,740);QTest.qWait(50)
        assert page.tree.isHeaderHidden() and page.tree.columnCount()==1
        assert page.detail.isHidden() and page.cancel_button.isHidden() and page.retry_button.isHidden()
        first=page.tree.topLevelItem(0);page.tree.setCurrentItem(first)
        window.grab().save(str(ROOT/'tmp'/f'minimal-tasks-{mode}.png'))
        page.tree.verticalScrollBar().setValue(120);position=page.tree.verticalScrollBar().value()
        for _ in range(5):page.refresh();app.processEvents()
        assert page.tree.topLevelItem(0) is first and page.tree.currentItem() is first
        assert page.tree.verticalScrollBar().value()==position
        page.details_button.click();assert page.detail.isVisible()
        page.details_button.click();assert page.detail.isHidden()
    page.clear();assert not page.nodes and page.tree.topLevelItemCount()==0
    window.close()
assert not errors,errors
print('PASS: headerless task rows, dark/light rendering, stable row identity and scroll, contextual actions and inline details')
