"""Exercise the embedded export dialog and screenshot multiselection."""
import json,os,sys,tempfile,time,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication,QFileDialog,QPushButton,QLineEdit
from PySide6.QtTest import QTest
from launcher.qtui.app import MainWindow
from tests.test_next_features import fixture

app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='export-ui-') as directory:
    root=Path(directory);repo,mods,_=fixture(root)
    (mods/'example.jar').write_bytes(b'mod');run=repo.run_dir('fixture')
    shots=run/'screenshots';shots.mkdir();(shots/'one.png').write_bytes(b'one');(shots/'two.png').write_bytes(b'two')
    window=MainWindow(root/'onionmcl.json',root);window.show();QTest.qWait(50)
    def wait(predicate):
        end=time.monotonic()+15
        while not predicate() and time.monotonic()<end:QTest.qWait(10)
        assert predicate(),'UI operation timed out'
    wait(lambda:not window.tasks.jobs)
    window.reload_versions();wait(lambda:not window.tasks.jobs);window.set_selected('fixture')
    window.export_modpack('fixture');dialog=window.subpages[-1]
    name=next(edit for edit in dialog.findChildren(QLineEdit) if edit.placeholderText()=='整合包名称');name.setText('演示包')
    output=root/'result.mrpack'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(output),'整合包 (*.mrpack)')):
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='导出').click()
        wait(lambda:output.is_file() and not window.tasks.jobs)
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read('modrinth.index.json'))['name']=='演示包'
        assert archive.read('overrides/mods/example.jar')==b'mod'
    window.navigate('instance');window.open_instance_tab('screenshots');browser=window.instance_workspace.pages['screenshots'].file_browser
    wait(lambda:len(browser.gallery.gallery_model.entries)==2 and not window.tasks.jobs)
    gallery=browser.gallery;gallery.selectionModel().select(gallery.gallery_model.index(0),QItemSelectionModel.SelectionFlag.Select)
    gallery.selectionModel().select(gallery.gallery_model.index(1),QItemSelectionModel.SelectionFlag.Select)
    entries=[index.data(256) for index in gallery.selectionModel().selectedIndexes()]
    assert len(entries)==2
    target=root/'selected';target.mkdir()
    with patch.object(QFileDialog,'getExistingDirectory',return_value=str(target)):
        gallery.export_selected(entries);wait(lambda:(target/'one.png').exists() and (target/'two.png').exists() and not window.tasks.jobs)
    assert (target/'one.png').read_bytes()==b'one'
    window.close()
print('PASS: modpack export and screenshot multiselection')
