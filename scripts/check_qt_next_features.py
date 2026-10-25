"""Actual UI paths for the next feature set, all filesystem/network data isolated."""
import os,sys,time,tempfile,json,threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox
from PySide6.QtTest import QTest
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.config import Config
from launcher.instance import InstanceStore
from launcher.storage import directory_key
from tests.test_next_features import fixture,jar,release,Catalog
from tests.test_workshop import png
app=QApplication([]);configure_fonts(app);exceptions=[]
def error_hook(kind,error,tb):exceptions.append(str(error));sys.__excepthook__(kind,error,tb)
sys.excepthook=error_hook
def wait(predicate,seconds=15):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate(),'UI task timed out'
def click(button):QTest.mouseClick(button,Qt.MouseButton.LeftButton);app.processEvents()
def quiet(window):QTest.qWait(50);wait(lambda:not window.tasks.jobs)

class LocalCatalog(Catalog):
    @contextmanager
    def cancellable(self,event,on_bytes=None):
        self.event=event;self.on_bytes=on_bytes
        try:yield
        finally:self.on_bytes=None
    def download_one(self,job):
        super().download_one(job)
        if getattr(self,'on_bytes',None):self.on_bytes(job.path.stat().st_size)

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='next-ui-') as directory:
    base=Path(directory);repo,folder,_=fixture(base)
    original=jar('a',depends={'lib':'>=1'});updated=jar('a','2.0',depends={'lib':'>=2'});libdata=jar('lib','2.0')
    old=release('a',original,date='2026-01-01');dep=release('lib',libdata,'2.0')
    new=release('a',updated,'2.0',deps=[dict(project_id='lib',version_id=dep['id'],dependency_type='required')])
    (folder/'a-old.jar').write_bytes(original)
    window=MainWindow(base/'onionmcl.json',base);errors=[];window.error=lambda e:errors.append(str(e));window.show();quiet(window)
    catalog=LocalCatalog([old,new,dep],{new['files'][0]['url']:updated,dep['files'][0]['url']:libdata});window.repo.downloader=catalog
    second=base/'other-game';version=second/'versions/fixture';version.mkdir(parents=True)
    (version/'fixture.json').write_text((repo.versions_dir/'fixture/fixture.json').read_text())
    window.game_libraries.add(second);window.instances.update('fixture',name='同名实例',favorite=True,tags=['生存'])
    other=InstanceStore(window.instances.path,second,window.config_obj.get('library_legacy_root'));other.update('fixture',name='同名实例',tags=['测试'])
    window.navigate('versions');app.processEvents();window.library_favorites.setCurrentIndex(1);assert window.version_tree.topLevelItemCount()==1
    window.library_tags.setCurrentIndex(window.library_tags.findData('生存'));assert window.version_tree.topLevelItemCount()==1
    star=window.version_tree.itemWidget(window.version_tree.topLevelItem(0),4);assert star.isChecked();filled=star.icon().pixmap(20,20).toImage()
    click(star);assert window.version_tree.topLevelItemCount()==0 and not window.instances.get('fixture').favorite
    window.library_favorites.setCurrentIndex(0);star=window.version_tree.itemWidget(window.version_tree.topLevelItem(0),4)
    assert not star.isChecked() and star.icon().pixmap(20,20).toImage()!=filled
    click(star);assert window.instances.get('fixture').favorite
    window.open_instance_overview();view=window.subpages[-1];quiet(window)
    assert view.tree.topLevelItemCount()==2
    view.only_favorites.setChecked(True);assert view.tree.topLevelItemCount()==1
    view.only_favorites.setChecked(False);view.query.setText('测试');assert view.tree.topLevelItemCount()==1
    view.tags_filter.setCurrentIndex(view.tags_filter.findData('测试'));view.only_favorites.setChecked(True);assert view.tree.topLevelItemCount()==0
    view.only_favorites.setChecked(False);assert view.tree.topLevelItemCount()==1
    click(view.use_button);quiet(window)
    assert directory_key(window.repo.game_dir)==directory_key(second) and window.selected_version=='fixture'
    assert window.instances.get('fixture').tags==['测试'] and not window.instances.get('fixture').favorite
    assert window.current_page=='home'
    assert window.switch_game_library(repo.game_dir);quiet(window);window.repo.downloader=catalog
    assert window.instances.get('fixture').favorite

    window.open_mod_manager('fixture');manager=window.subpages[-1];quiet(window)
    assert manager.issues.topLevelItemCount()>=1
    assert 'Minecraft 1.21.1' in manager.context_label.text() and 'Java 21' in manager.context_label.text()
    for i in range(manager.issues.topLevelItemCount()):
        node=manager.issues.topLevelItem(i)
        if node.data(0,Qt.ItemDataRole.UserRole)=='lib':manager.issues.setCurrentItem(node);break
    assert manager.search_button.isEnabled()
    click(manager.updates_button);quiet(window)
    assert manager.versions.topLevelItemCount()==1 and manager.plan_button.isEnabled()
    click(manager.plan_button);quiet(window)
    assert len(manager.plan['entries'])==2 and manager.apply_button.isEnabled()
    for mode in ('light','dark'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        for width,height in ((900,600),(1200,800)):
            window.resize(width,height);QTest.qWait(40)
            assert window.width()==width and window.height()==height,('Feature page prevents resizing',window.size())
            assert manager.rect().contains(manager.apply_button.mapTo(manager,manager.apply_button.rect().center()))
            window.grab().save(str(ROOT/'tmp'/('next-mod-plan-'+mode+('-small' if width==900 else '')+'.png')))
    catalog.fail=True
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):click(manager.apply_button)
    quiet(window);assert errors and (folder/'a-old.jar').read_bytes()==original;errors.clear()
    failed=window.task_history.items[-1];assert failed['state']=='failed'
    catalog.fail=False;window.open_task_center();center=window.download_tasks;center.refresh()
    assert window.current_page=='download' and window.nav['tasks'].isChecked()
    assert center.current()['id']==failed['id'] and center.retry_button.isEnabled()
    click(center.retry_button);quiet(window)
    assert (folder/'a-2.0.jar').read_bytes()==updated and (folder/'lib-2.0.jar').read_bytes()==libdata
    assert window.task_history.items[-1]['state']=='complete'
    center.refresh();window.grab().save(str(ROOT/'tmp/next-task-center.png'))
    window.open_mod_manager('fixture');manager=window.subpages[-1];quiet(window)
    assert not [manager.issues.topLevelItem(i) for i in range(manager.issues.topLevelItemCount()) if manager.issues.topLevelItem(i).text(0)=='需处理']
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):click(manager.undo_button)
    quiet(window);assert (folder/'a-old.jar').read_bytes()==original and not (folder/'a-2.0.jar').exists()
    manager.reject();window.preflight('fixture');health=window.subpages[-1];quiet(window)
    assert any('缺少 lib' in health.tree.topLevelItem(i).text(0) for i in range(health.tree.topLevelItemCount()))
    health.reject();logs=window.repo.run_dir('fixture')/'logs';logs.mkdir(exist_ok=True)
    (logs/'latest.log').write_text('java.lang.OutOfMemoryError: Java heap space access_token=SECRET_VALUE',encoding='utf-8')
    window.diagnose();diagnosis=window.subpages[-1];quiet(window)
    assert '内存不足' in diagnosis.report and 'SECRET_VALUE' not in diagnosis.report
    diagnosis.reject()

    window.navigate('tools');window.open_tools_tab('skins');wardrobe=window.workshop.views['skins']
    source=base/'skin.png';source.write_bytes(png());skin=wardrobe.library.import_skin(source);wardrobe.refresh();QTest.qWait(50)
    star=next(b for b in wardrobe.findChildren(QPushButton) if b.isVisible() and b.accessibleName()=='收藏')
    empty_star=star.icon().pixmap(20,20).toImage();assert not star.isChecked()
    click(star);assert wardrobe.library.is_favorite(skin);QTest.qWait(40)
    filled_star=next(b for b in wardrobe.findChildren(QPushButton) if b.isVisible() and b.accessibleName()=='取消收藏')
    assert filled_star.isChecked() and filled_star.icon().pixmap(20,20).toImage()!=empty_star
    wardrobe.favorites_only.setCurrentIndex(1);QTest.qWait(50);assert wardrobe.path==skin
    wardrobe.query.setText('no-such-skin');QTest.qWait(30);assert wardrobe.path is None and wardrobe.skin_count.text()=='0 / 1'
    wardrobe.query.clear();QTest.qWait(30);assert wardrobe.path==skin
    star=next(b for b in wardrobe.findChildren(QPushButton) if b.isVisible() and b.accessibleName()=='取消收藏')
    click(star);assert wardrobe.path is None and not wardrobe.apply.isEnabled() and not wardrobe.upload.isEnabled()

    # Background a real worker and cancel it from the task center, not from its dialog.
    def long_work(job):
        from launcher.download import DownloadCancelled
        end=time.monotonic()+10
        while time.monotonic()<end:
            if job.cancel.wait(.01):raise DownloadCancelled('fixture cancellation')
        raise RuntimeError('Task was not cancelled')
    job=window.task('下载取消测试',long_work);dialog=window.active_task
    click(next(b for b in dialog.findChildren(QPushButton) if b.text()=='后台运行'))
    assert not dialog.isVisible() and not job.cancel.is_set()
    window.open_task_center();center.refresh();click(center.cancel_button);quiet(window)
    assert window.task_history.items[-1]['state']=='cancelled'
    assert not errors,errors
    # The failing fixture's modal error was intercepted, and no real network/login/game ran.
    window.close();restored=MainWindow(base/'onionmcl.json',base);restored.show();quiet(restored)
    assert any(item['state']=='cancelled' for item in restored.task_history.items)
    assert restored.instances.get('fixture').favorite and restored.instances.get('fixture').tags==['生存']
    restored.close()
assert not exceptions,exceptions
print('PASS: cross-folder same-name selection, tags/favorites, dependency/update/preview, failed-download retry, transaction undo, preflight/diagnosis, skin favorites, background cancellation and restart')
