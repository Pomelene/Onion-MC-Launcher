"""Offscreen confirmation/catalog/card/browser routing using a fake web surface."""
import os,sys,json,time,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt'),str(ROOT/'tests')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Signal,QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QPushButton,QLabel
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from test_club_services import catalog
from launcher.qtui.club_services import ServiceConfirmation,ServiceSession
from launcher.club_services import CONFIRMATION

class FakeWeb(QWidget):
    urlChanged=Signal(QUrl);titleChanged=Signal(str);loadProgressChanged=Signal(int);loadingChanged=Signal(object)
    def __init__(self):super().__init__();self.urls=[];self.stops=0
    def setUrl(self,url):self.urls.append(url.toString());self.urlChanged.emit(url);self.titleChanged.emit('网页测试');self.loadProgressChanged.emit(100)
    def canGoBack(self):return len(self.urls)>1
    def goBack(self):pass
    def reload(self):self.setUrl(QUrl(self.urls[-1]))
    def stop(self):self.stops+=1

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def hook(kind,error,tb):errors.append(str(error));traceback.print_exception(kind,error,tb)
sys.excepthook=hook
def wait(window):
    app.processEvents();end=time.monotonic()+20
    while window.tasks.jobs and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert not window.tasks.jobs and not errors,(errors,window.tasks.jobs)
def snapshot(window,name):
    window.sync_navigation_motion(False);app.processEvents();image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);window.render(image)
    assert image.save(str(ROOT/'docs/screens'/name))

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='club-ui-') as folder:
    base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    window=MainWindow(config.path,base);window.error=lambda error:errors.append(str(error));window.show();wait(window);window.navigate('tools')
    with patch.object(ServiceConfirmation,'exec',return_value=QDialog.DialogCode.Rejected),patch('launcher.club_services.fetch_catalog') as fetch:
        window.open_tools_tab('services');assert not fetch.called and getattr(window,'tools_tab','skins')=='skins'
    service=window.workshop.views['services'];service.web_factory=FakeWeb
    with patch.object(ServiceConfirmation,'exec',return_value=QDialog.DialogCode.Accepted) as confirm,patch('launcher.club_services.fetch_catalog',side_effect=lambda:catalog()) as fetch:
        window.open_tools_tab('services');wait(window)
        assert confirm.call_count==1
        dialog=ServiceConfirmation(window);dialog.show();app.processEvents()
        assert any(item.text()==CONFIRMATION for item in dialog.findChildren(QLabel))
        assert dialog.windowFlags() & __import__('PySide6.QtCore',fromlist=['Qt']).Qt.WindowType.FramelessWindowHint
        image=QImage(dialog.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);dialog.render(image)
        assert image.save(str(ROOT/'docs/screens/qt-thunion-service-confirmation.png'));dialog.close()
        assert fetch.call_count==1 and service.catalog and service.browser is None
        assert len(service.buttons)==2
        assert any('阅读社团文档'==item.text() for item in service.findChildren(QLabel))
        for mode in ('dark','light'):
            window.config_obj.set('color_mode',mode);window.apply_appearance()
            for width in (1100,1440):window.resize(width,900);snapshot(window,f'qt-thunion-services-{mode}-{width}.png')
        next(button for button in service.tools.findChildren(QPushButton) if button.text()=='打开' and button.isVisible()).click()
        assert service.browser and service.browser.view.urls==['https://wiki.thunion.club/']
        assert not service.browser.isWindow() and service.stack.currentWidget() is service.browser
        app.processEvents();assert window.sidebar.isHidden() and service.heading.isHidden() and service.status.isHidden()
        browser=service.browser;assert browser.status.isHidden() and browser.progress.isHidden()
        assert browser.container.width()>=window.width()-20
        assert browser.container.height()>=window.height()-160
        snapshot(window,'qt-thunion-web-expanded.png')
        browser.navigation.click();app.processEvents();assert not window.sidebar.isHidden()
        assert browser.navigation.text()=='展开网页'
        browser.navigation.click();app.processEvents();assert window.sidebar.isHidden()
        service.return_to_catalog();app.processEvents();assert not window.sidebar.isHidden() and not service.heading.isHidden()
        service.buttons[1][0].click();app.processEvents()
        assert service.browser is None and any('平移缩放服务器地图'==item.text() for item in service.findChildren(QLabel))
        next(button for button in service.tools.findChildren(QPushButton) if button.text()=='打开' and button.isVisible()).click()
        assert service.browser.view.urls==['https://map.thunion.club/']
        service.return_to_catalog();app.processEvents()
        assert any('在线地图，提供离线导航模组下载'==item.text() for item in service.findChildren(QLabel))
        next(button for button in service.tools.findChildren(QPushButton) if button.text()=='打开' and button.isVisible() and 'Atlas' in button.parentWidget().findChildren(QLabel)[0].text()).click()
        assert service.browser.view.urls==['https://atlas.thunion.net/']
        window.open_tools_tab('services');wait(window);assert fetch.call_count==1 and confirm.call_count==1 and service.browser is None
        assert window.club_service_session.path.is_file()
        # Rebuilding the Workshop must reuse the same process session and cached JSON.
        session=window.club_service_session
        window.navigate('home');window.navigate('tools');window.open_tools_tab('services');wait(window)
        assert window.club_service_session is session and fetch.call_count==1 and confirm.call_count==1
        service=window.workshop.views['services'];assert service.catalog==catalog()
    # v2 is entirely data-driven: ordering, list presentation and each action.
    import hashlib
    from launcher.club_services import parse_catalog
    body=b'fixture member pack';download={'id':'basic','title':'三周目快速上服基础包','description':'下载后手动导入','url':'https://example.test/263THUnionBasic.mrpack','action':'download','filename':'263THUnionBasic.mrpack','size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'button_text':'下载基础包','badge':'26.3'}
    payload=catalog();payload['schema_version']=2
    payload['categories'].insert(0,{'id':'sharing','title':'部员分享','description':'部员的分享内容','layout':'list','icon':'tools','show_urls':False,'tools':[
        download,{'id':'external','title':'外部项目','description':'系统浏览器','url':'https://github.com/Pomelene/Litematica-Flex','action':'external'},
        {'id':'copy','title':'复制入口','description':'仅复制网址','url':'https://atlas.thunion.net/guide.html','action':'copy'}]})
    service.catalog=parse_catalog(payload);service.render_categories();app.processEvents()
    assert service.buttons[0][1]=='sharing' and service.selected_category['id']=='sharing'
    from launcher.qtui.widgets import ContentRow
    assert len(service.tools.findChildren(ContentRow))==3
    with patch('launcher.qtui.club_services.QDesktopServices.openUrl',return_value=True) as external:
        service.activate_tool(payload['categories'][0]['tools'][1]);assert external.call_count==1
    service.activate_tool(payload['categories'][0]['tools'][2]);assert QApplication.clipboard().text()=='https://atlas.thunion.net/guide.html'
    def save_download(job,progress=None):
        job.path.parent.mkdir(parents=True,exist_ok=True);job.path.write_bytes(body)
        if progress:progress(len(body),len(body))
        return True
    imported=[];original_installed=window.installed;window.installed=imported.append
    with patch.object(window.repo.downloader,'download_one',side_effect=save_download):
        service.activate_tool(download);wait(window)
    assert service.download_path(download).read_bytes()==body and imported==[]
    with patch('launcher.modpack.import_modpack',return_value='member-fixture') as install:
        service.import_tool(download);wait(window);assert imported==['member-fixture'] and install.call_count==1
        service.download_path(download).write_bytes(b'broken')
        prior_error=window.error;window.error=lambda error:None
        service.import_tool(download);wait(window);assert install.call_count==1
        window.error=prior_error
    window.installed=original_installed
    snapshot(window,'qt-thunion-member-sharing-list.png')
    payload['categories'][0]['layout']='cards';service.catalog=parse_catalog(payload);service.render_categories();app.processEvents()
    snapshot(window,'qt-thunion-member-sharing-cards.png')

    # A new launcher session prompts/syncs again; failure keeps the good local catalog.
    window.club_service_session=ServiceSession(window)
    with patch.object(ServiceConfirmation,'exec',return_value=QDialog.DialogCode.Accepted) as confirm,patch('launcher.club_services.fetch_catalog',side_effect=RuntimeError('目录测试失败')) as fetch:
        from launcher.qtui.club_services import ClubServices
        offline=ClubServices(window);assert offline.enter();wait(window)
        assert offline.catalog==catalog() and '目录测试失败' in offline.status.text()
        assert offline.enter();wait(window);assert confirm.call_count==1 and fetch.call_count==1
        offline.deleteLater()
    # Leaving during a pending request still completes the one session sync.
    window.club_service_session=ServiceSession(window)
    with patch.object(ServiceConfirmation,'exec',return_value=QDialog.DialogCode.Accepted) as confirm,patch('launcher.club_services.fetch_catalog',return_value=catalog()) as fetch:
        pending=ClubServices(window);assert pending.enter();pending.hide();assert pending.enter();wait(window)
        assert pending.catalog==catalog() and confirm.call_count==1 and fetch.call_count==1
        pending.deleteLater()
    # Explicit preview mode must never fetch or overwrite the normal cache.
    window.club_service_session=ServiceSession(window)
    preview_session=window.club_service_session;preview_session.preview_path.parent.mkdir(parents=True,exist_ok=True)
    preview_session.preview_path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    original_cache=preview_session.path.read_bytes()
    with patch.object(ServiceConfirmation,'exec',return_value=QDialog.DialogCode.Accepted),patch('launcher.club_services.fetch_catalog') as fetch:
        preview=ClubServices(window);assert preview.enter();wait(window)
        assert preview.session.preview and preview.buttons[0][1]=='sharing' and not fetch.called
        assert '本地预览' in preview.status.text() and preview_session.path.read_bytes()==original_cache
        preview.deleteLater()
    window.navigate('home');wait(window);window.close();assert not errors,errors
print(json.dumps({'result':'pass','confirmation_once_per_session':True,'sync_once_per_session':True,'cached_offline_fallback':True,'description_before_navigation':True,'embedded_tools':True,'fixtures_only':True}))
