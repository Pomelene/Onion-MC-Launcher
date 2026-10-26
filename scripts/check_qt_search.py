"""Offline provider requests and default browsing through the real download page."""
import os,sys,json,time,tempfile,threading
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import ContentRow,configure_fonts
from launcher.catalog_search import search_terms
app=QApplication([]);configure_fonts(app);errors=[];requests=[]
def error_hook(kind,value,tb):errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=error_hook
def wait(predicate):
    end=time.monotonic()+10
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert predicate() and not errors,errors
slow=threading.Event();release=threading.Event();fail=False
def provider(url,*args,**kwargs):
    if url.endswith('/tag/category'):
        return [dict(name='optimization',project_type='mod'),dict(name='realistic',project_type='shader')]
    assert '/search?' in url,url
    params=parse_qs(urlparse(url).query,keep_blank_values=True);requests.append(params)
    if params['query']==['slow']:slow.set();release.wait(5)
    if fail:raise OSError('offline fixture')
    offset=int(params['offset'][0]);text=params['query'][0] or 'Popular'
    return dict(total_hits=60,hits=[dict(project_id=f'{text}-{offset+i}',title=f'{text} {offset+i}',description='Fixture description') for i in range(20)])
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='search-ui-') as tmp:
    base=Path(tmp);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'game'))
    for vid,game in [('Custom instance','26.3'),('Second instance','1.21.1')]:
        folder=base/'game/versions'/vid;folder.mkdir(parents=True)
        (folder/(vid+'.json')).write_text(json.dumps(dict(id=vid,onionGameVersion=game,mainClass='Main',libraries=[dict(name='net.fabricmc:fabric-loader:0.19.5')])),encoding='utf-8')
    window=MainWindow(config.path,base);window.show();QTest.qWait(50);wait(lambda:not window.tasks.jobs)
    assert window.set_selected('Custom instance',refresh_page=False),window.versions
    with patch.object(window.repo.downloader,'fetch_json',side_effect=provider):
        window.choose_download_kind('mod');wait(lambda:not window.tasks.jobs and bool(requests));browser=window.download_browser
        assert requests[0]['query']==[''] and requests[0]['index']==['relevance']
        assert ['versions:26.3'] in json.loads(requests[0]['facets'][0]),(requests,browser.game.text(),window.selected_version)
        assert ['categories:fabric'] in json.loads(requests[0]['facets'][0])
        assert browser.filters.isHidden() and browser.last_search
        count=len(requests);browser.results.verticalScrollBar().setValue(120);position=browser.results.verticalScrollBar().value()
        window.navigate('home');window.choose_download_kind('mod');QTest.qWait(50)
        assert len(requests)==count and browser.results.verticalScrollBar().value()==position
        browser.filter_button.click();wait(lambda:browser.categories_loaded)
        assert browser.category.count()==2 and browser.category.findData('realistic')==-1
        browser.category.setCurrentIndex(1);browser.category.activated.emit(1)
        browser.sort.setCurrentIndex(browser.sort.findData('downloads'));browser.sort.activated.emit(browser.sort.currentIndex())
        wait(lambda:len(requests)>count and not window.tasks.jobs and not browser.search_timer.isActive())
        assert len(requests)==count+1 and requests[-1]['index']==['downloads']
        assert ['categories:optimization'] in json.loads(requests[-1]['facets'][0])
        browser.query.setText('钠');QTest.keyClick(browser.query,Qt.Key.Key_Return);wait(lambda:not window.tasks.jobs)
        assert requests[-1]['query']==['Sodium']
        browser.next.click();wait(lambda:not window.tasks.jobs);assert requests[-1]['offset']==['20']
        browser.query.setText('unknown 中文');browser.go.click();wait(lambda:not window.tasks.jobs)
        assert requests[-1]['query']==['unknown 中文'] and requests[-1]['offset']==['0']
        browser.query.setText('slow');browser.search();wait(slow.is_set)
        browser.query.setText('fast');browser.search();wait(lambda:browser.last_search and browser.last_search[0]=='fast')
        release.set();wait(lambda:not window.tasks.jobs)
        assert all(row.text.title.startswith('fast') for row in browser.results.findChildren(ContentRow))
        browser.target.setCurrentIndex(browser.target.findData('Second instance'))
        wait(lambda:browser.last_search and browser.last_search[3]=='Second instance')
        assert ['versions:1.21.1'] in json.loads(requests[-1]['facets'][0])
        browser.reset.click();wait(lambda:browser.last_search and browser.last_search[4:]==('','relevance'))
        browser.query.clear();wait(lambda:browser.last_search and browser.last_search[0]=='')
        fail=True;browser.search();wait(lambda:not window.tasks.jobs)
        assert browser.message.text() and browser.go.isEnabled()
        fail=False;browser.go.click();wait(lambda:not window.tasks.jobs);assert not browser.message.text()
        for mode in ('dark','light'):
            window.config_obj.set('color_mode',mode);window.apply_appearance();window.resize(900,600);QTest.qWait(40)
            for widget in (browser.go,browser.reset,browser.sort,browser.next):
                assert window.rect().contains(widget.mapTo(window,widget.rect().bottomRight()))
            window.grab().save(str(ROOT/'tmp'/f'search-{mode}.png'))
        window.choose_download_kind('modpack');wait(lambda:window.download_browser.last_search is not None and not window.tasks.jobs)
        assert json.loads(requests[-1]['facets'][0])==[['project_type:modpack']]
    window.close()
assert search_terms('mod','  钠　 ' )=='Sodium'
assert search_terms('shader','钠')=='钠'
assert not errors,errors
print('PASS: default results, real instance version, filters/sorts, Chinese aliases, page reset, debounce, stale responses, retry, retained results and compact layout')
