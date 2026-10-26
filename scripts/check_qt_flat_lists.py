"""Dense-list layout and real selection paths in isolated, offline Qt fixtures."""
import os,sys,time,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.lists import FlatTreeWidget,META_ROLE
from launcher.qtui.installer import InstallDialog
from launcher.qtui.project_versions import ProjectVersions
from launcher.version import VersionManifest
from launcher.config import Config
app=QApplication([]);configure_fonts(app);errors=[]
def report_error(kind,value,trace):errors.append(str(value));sys.__excepthook__(kind,value,trace)
sys.excepthook=report_error
def idle(window):
    app.processEvents();end=time.monotonic()+15
    while window.tasks.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not window.tasks.jobs,'Fixture task timed out'
    assert not errors,errors
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='flat-list-ui-') as tmp:
    base=Path(tmp);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    window=MainWindow(config.path,base);window.show();idle(window)
    manifest=VersionManifest({'versions':[{'id':f'1.21.{i}','type':'release','releaseTime':'2026-10-01T00:00:00Z'} for i in range(60)]})
    with patch.object(window.repo,'fetch_manifest',return_value=manifest):
        install=InstallDialog(window);window.show_subpage(install);idle(window)
    assert isinstance(install.tree,FlatTreeWidget) and install.tree.isHeaderHidden() and install.tree.columnCount()==1
    assert install.tree.topLevelItemCount()==60 and install.tree.topLevelItem(0).data(0,META_ROLE)
    assert install.loader_panel.isHidden() and install.build.isHidden()
    assert not any(label.text() in ('安装选项','可用加载器版本','安装 Minecraft','下载位置') for label in install.findChildren(QLabel))
    for mode in ('dark','light'):
        for font_size in (14,20):
            window.config_obj.update({'color_mode':mode,'font_size':font_size});window.apply_appearance()
            for width,height in ((900,600),(1280,800)):
                window.resize(width,height);QTest.qWait(40)
                assert window.width()==width and window.height()==height,(mode,font_size,window.size())
                assert install.tree.viewport().height()>=180,install.tree.viewport().size()
                assert install.tree.visualItemRect(install.tree.topLevelItem(0)).height()>=44
                assert window.rect().contains(install.install_button.mapTo(window,install.install_button.rect().bottomRight())),(mode,font_size,window.size(),window.stack.geometry(),[(type(window.stack.widget(i)).__name__,window.stack.widget(i).minimumSizeHint(),window.stack.widget(i).minimumSize()) for i in range(window.stack.count())])
                assert install.install_button.isEnabled()
                window.grab().save(str(ROOT/'tmp'/f'flat-installer-{mode}-{font_size}-{width}.png'))
    window.config_obj.set('font_size',14);window.apply_appearance();window.resize(900,600);app.processEvents()
    with patch('launcher.install.fabric.list_loaders',return_value=[{'loader':{'version':f'0.19.{i}','stable':True}} for i in range(12)]):
        install.loader.setCurrentIndex(1);install.fetch_loaders();idle(window)
    assert install.loader_panel.isVisible() and install.loader_tree.topLevelItemCount()==12
    assert install.tree.viewport().height()>=180 and install.loader_tree.viewport().height()>=180
    assert install.tree.width()>=240 and install.loader_tree.width()>=240
    app.processEvents()
    assert install.tree.mapTo(install,install.tree.rect().topLeft()).y()==install.loader_tree.mapTo(install,install.loader_tree.rect().topLeft()).y()
    assert abs(install.tree.height()-install.loader_tree.height())<=2
    install.loader_tree.setCurrentItem(install.loader_tree.topLevelItem(3));assert install.build.text()=='0.19.3'
    window.grab().save(str(ROOT/'tmp/flat-installer-fabric-900.png'))
    half_width=install.tree.width();install.loader.setCurrentIndex(0);app.processEvents()
    assert install.loader_panel.isHidden() and install.build.text()=='' and install.tree.width()>half_width*1.6
    install.reject()
    versions=[dict(id=str(i),version_number='26.3-fabric-long-version-'+str(i),version_type='release',date_published='2026-10-01',game_versions=['26.3'],loaders=['fabric'],files=[dict(filename='a-very-long-file-name-'+str(i)+'.jar')]) for i in range(20)]
    with patch('launcher.qtui.project_versions.versions',return_value=versions):
        page=ProjectVersions(window,'fixture','项目版本 / 中文支持','mod','26.3','fabric','');window.show_subpage(page);idle(window)
    assert isinstance(page.tree,FlatTreeWidget) and page.tree.columnCount()==1 and page.tree.isHeaderHidden()
    assert page.tree.topLevelItemCount()==20 and page.install_button.isEnabled()
    assert '.jar' in page.tree.topLevelItem(0).toolTip(0)
    window.grab().save(str(ROOT/'tmp/flat-project-versions-900.png'));page.reject()
    window.navigate('versions');assert isinstance(window.version_tree,FlatTreeWidget)
    window.close()
assert not errors,errors
print('PASS: shared flat lists, installer 900x600 / 1280x800, 14px / 20px, dark / light, optional loader panel, explicit loader selection and catalog rows')
