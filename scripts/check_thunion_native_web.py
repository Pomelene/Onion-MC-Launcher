"""Hidden Windows WebView2 smoke test; no desktop window, login or game launch."""
import os,sys,json,time,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='windows'
profile=tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='thunion-web-profile-')
os.environ['WEBVIEW2_USER_DATA_FOLDER']=profile.name
from launcher.qtui.web_tools import initialize_webview
initialize_webview()
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
from PySide6.QtWebView import QWebView,QWebViewSettings

app=QApplication([]);root=QWidget();root.resize(1100,700);layout=QVBoxLayout(root)
view=QWebView();container=QWidget.createWindowContainer(view,root);layout.addWidget(container)
root.winId();container.winId();view.create();results=[];states=[]
view.loadingChanged.connect(lambda info:states.append((info.status().name,info.url().toString(),info.errorString())))
def wait(predicate,timeout=35):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert predicate(),str(states)
    assert not root.isVisible() and not container.isVisible()

view.loadHtml('<html><head><title>Onion Native WebView2</title></head><body>THUnion embedded web tools</body></html>')
wait(lambda:any(state[0] in ('Succeeded','Failed') for state in states))
assert states[-1][0]=='Succeeded',states
dom=[];view.runJavaScript('document.title',lambda title:dom.append(title));wait(lambda:bool(dom))
assert dom[-1]=='Onion Native WebView2',dom
from launcher.club_services import fetch_catalog
for url in [tool['url'] for category in fetch_catalog()['categories'] for tool in category['tools']]:
    states.clear();view.setUrl(QUrl(url));wait(lambda:any(state[0] in ('Succeeded','Failed') for state in states))
    result={'url':url,'status':states[-1][0],'error':states[-1][2],'title':view.title()}
    if result['status']=='Succeeded':
        data=[];view.runJavaScript('JSON.stringify({title:document.title,body:document.body.innerText.length,frames:Array.from(document.querySelectorAll("frame")).map(frame=>frame.src),webgl:!!document.createElement("canvas").getContext("webgl2")})',lambda value:data.append(value))
        wait(lambda:bool(data));result['dom']=data[-1]
    results.append(result)
view.stop();root.close();view.destroy();app.processEvents()
report={'native_webview2_dom':'pass','visible_windows':False,'sites':results}
(ROOT/'tmp/thunion-native-web-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
# WebView2 can retain its profile while child processes finish; keep this test
# profile under ignored tmp rather than deleting a live browser data directory.
profile._finalizer.detach()
