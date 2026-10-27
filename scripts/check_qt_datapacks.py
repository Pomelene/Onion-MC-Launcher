"""Exercise the embedded data-pack page and version changelog without network."""
import json,os,sys,tempfile,time,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.project_versions import ProjectVersions
from launcher.worlds import WorldInfo

app=QApplication([])
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='datapack-ui-') as directory:
    root=Path(directory);config=Config(root/'onionmcl.json');config.update({'game_dir':str(root/'game'),'check_launcher_updates':False})
    window=MainWindow(config.path,root);window.show()
    world=root/'game/versions/fixture/saves/world';packs=world/'datapacks';packs.mkdir(parents=True)
    (world.parents[1]/'fixture.json').write_text(json.dumps({'id':'fixture','onionGameVersion':'1.20.4','mainClass':'Main'}))
    (world/'level.dat').write_bytes(b'fixture')
    with zipfile.ZipFile(packs/'example.zip','w') as archive:archive.writestr('pack.mcmeta',json.dumps({'pack':{'description':'示例'}}))
    window.manage_datapacks(WorldInfo(world,'世界'),'fixture');page=window.subpages[-1]
    end=time.monotonic()+10
    while window.tasks.jobs and time.monotonic()<end:QTest.qWait(10)
    assert not window.tasks.jobs
    assert page.navigation_title=='数据包 · 世界' and page.results.count()>=2
    entry={'id':'version1','version_number':'1','game_versions':['1.20.4'],'loaders':['datapack'],
           'files':[{'filename':'new.zip','primary':True}]}
    def fake_download(downloader,version,target):
        output=target/'new.zip'
        with zipfile.ZipFile(output,'w') as archive:archive.writestr('pack.mcmeta',json.dumps({'pack':{'description':'下载'}}))
        return output
    with patch('launcher.catalog.search',return_value={'hits':[{'project_id':'p1','title':'数据包'}],'total_hits':1}),\
         patch('launcher.qtui.project_versions.versions',return_value=[entry]),\
         patch('launcher.catalog.versions',return_value=[entry]),patch('launcher.catalog.download_version',side_effect=fake_download):
        page.search_online();search=window.subpages[-1]
        end=time.monotonic()+10
        while (not search.tree.topLevelItemCount() or window.tasks.jobs) and time.monotonic()<end:QTest.qWait(10)
        assert search.tree.topLevelItemCount()==1
        search.choose(search.tree.topLevelItem(0));version_page=window.subpages[-1]
        end=time.monotonic()+10
        while (version_page.loading or not version_page.tree.topLevelItemCount()) and time.monotonic()<end:QTest.qWait(10)
        assert version_page.install_button.isEnabled();version_page.install()
        end=time.monotonic()+10
        while (window.tasks.jobs or not (packs/'new.zip').exists()) and time.monotonic()<end:QTest.qWait(10)
        assert (packs/'new.zip').is_file()
    window.go_back();window.close()

class Pending:
    def submit(self,work,done,failed):self.done=done
class Owner(QWidget):
    def __init__(self):
        super().__init__();self.tasks=Pending();self.repo=SimpleNamespace(downloader=None)
        self.instances=SimpleNamespace(display_name=lambda vid:'实例')
owner=Owner();view=ProjectVersions(owner,'p','项目','mod','1.21','fabric','fixture');view.show();QTest.qWait(50)
owner.tasks.done([{'id':'v1','version_number':'1','game_versions':['1.21'],'loaders':['fabric'],'files':[{'filename':'a.jar'}],'changelog':'更新内容'}])
assert view.changelog_button.isVisible()
view.toggle_changelog();assert view.changelog.isVisible() and view.changelog.toPlainText()=='更新内容'
view.reject();owner.close()
print('PASS: embedded data packs and version changelog')
