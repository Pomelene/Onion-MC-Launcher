"""Offscreen task window checks; no network, real accounts or game directories."""
import os,sys,tempfile,time,threading,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def hook(kind,error,tb):errors.append(str(error));traceback.print_exception(kind,error,tb)
sys.excepthook=hook
def wait(predicate):
    end=time.monotonic()+15
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert predicate() and not errors,errors

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='task-dialog-') as folder:
    base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    window=MainWindow(config.path,base);window.show();wait(lambda:not window.tasks.jobs)
    gate=threading.Event()
    def work(job):
        job.emit('读取整合包信息');job.emit('下载必要文件');job.emit((128,400))
        job.transferred(1024*1024);gate.wait(10)
    job=window.task('安装整合包',work);dialog=window.active_task
    wait(lambda:dialog.progress.value()==320 and dialog.total_bytes==1024*1024)
    assert dialog.isWindow() and dialog.isModal() and dialog not in window.subpages
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.rows[-2][1].state=='done' and dialog.current[1].state=='active'
    assert dialog.width()<800 and dialog.height()<550
    assert dialog.amount.text()=='128 / 400  ·  32%' and 'MiB' in dialog.transferred.text()
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance();app.processEvents()
        image=QImage(dialog.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);dialog.render(image)
        assert image.save(str(ROOT/'docs/screens'/f'qt-task-dialog-{mode}.png'))
    # File counts cannot change measured network traffic or speed.
    dialog.update_progress((8000,10000));assert dialog.total_bytes==1024*1024
    for index in range(100):dialog.update_progress(f'处理阶段 {index}')
    assert len(dialog.rows)==80
    dialog.reject();assert job.cancel.is_set() and not dialog.cancel_button.isEnabled()
    dialog.update_progress('late stage');assert dialog.message.text()=='正在取消，请稍候…'
    gate.set();wait(lambda:not window.tasks.jobs);assert not dialog.isVisible() and window.active_task is None
    failures=[];window.error=lambda error:failures.append(str(error))
    def fail(job):job.emit('校验文件');raise RuntimeError('校验失败测试')
    window.task('下载失败测试',fail);failed=window.active_task
    wait(lambda:not window.tasks.jobs);assert failures==['校验失败测试'] and failed.current[1].state=='failed'
    # A subsequent job must not inherit cancellation or received byte counters.
    window.task('下载完成测试',lambda job:job.emit('安装完成'));success=window.active_task
    wait(lambda:not window.tasks.jobs);assert success.current[1].state=='done' and success.total_bytes==0
    window.close();assert not errors,errors
print('PASS: compact modal, stage history, network bytes, cancellation, failure, success, dark/light')
