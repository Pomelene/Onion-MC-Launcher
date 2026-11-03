"""Small native WebView2 host, isolated from launcher accounts and commands."""
import os
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget,QLineEdit,QProgressBar
from .widgets import column,row,label,button
from ..club_services import web_url


def initialize_webview():
    os.environ['QT_WEBVIEW_PLUGIN']='webview2'
    from ..paths import app_root
    os.environ.setdefault('WEBVIEW2_USER_DATA_FOLDER',str(app_root()/'.onion/webview/thunion'))
    from PySide6.QtWebView import QtWebView
    QtWebView.initialize()


class WebTool(QWidget):
    def __init__(self,tool,return_to_catalog,view_factory=None,toggle_navigation=None):
        super().__init__();self.tool=tool;body=column(self,0,0)
        self.toolbar=QWidget();self.toolbar.setFixedHeight(48);toolbar=row(self.toolbar,8,6)
        toolbar.addWidget(button('工具目录',return_to_catalog,glyph='back'))
        self.back=button('后退',lambda:self.view.goBack());toolbar.addWidget(self.back)
        refresh=button('',lambda:self.view.reload(),glyph='refresh');refresh.setToolTip('刷新网页');refresh.setAccessibleName('刷新网页');refresh.setFixedSize(32,32);toolbar.addWidget(refresh)
        self.address=QLineEdit();self.address.setReadOnly(True);self.address.setMinimumWidth(80);self.address.setAccessibleName('网页地址');toolbar.addWidget(self.address,1)
        toolbar.addWidget(button('停止',lambda:self.view.stop()))
        if toggle_navigation:
            self.navigation=button('显示导航',toggle_navigation);toolbar.addWidget(self.navigation)
        body.addWidget(self.toolbar)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setFixedHeight(2);self.progress.setTextVisible(False);self.progress.hide();body.addWidget(self.progress)
        self.status=label('','muted',True);self.status.setContentsMargins(10,6,10,6);self.status.hide();body.addWidget(self.status)
        if view_factory:
            self.view=view_factory();self.container=self.view
        else:
            from PySide6.QtWebView import QWebView,QWebViewSettings
            self.view=QWebView();settings=self.view.settings()
            settings.setAttribute(QWebViewSettings.WebAttribute.AllowFileAccess,False)
            settings.setAttribute(QWebViewSettings.WebAttribute.LocalContentCanAccessFileUrls,False)
            self.container=QWidget.createWindowContainer(self.view,self)
            self.container.setMinimumSize(0,0)
        body.addWidget(self.container,1)
        self.view.urlChanged.connect(self.url_changed);self.view.titleChanged.connect(self.title_changed)
        self.view.loadProgressChanged.connect(self.progress_changed);self.view.loadingChanged.connect(self.loading_changed)
        self.view.setUrl(QUrl(web_url(tool['url'])))

    def url_changed(self,url):
        text=url.toString();self.address.setText(text);self.back.setEnabled(self.view.canGoBack())
        try:web_url(text)
        except ValueError:self.view.stop();self.status.setText('已停止不支持的网页地址');self.status.show()
    def title_changed(self,title):self.address.setToolTip(title or self.tool['title'])
    def progress_changed(self,value):self.progress.setValue(value);self.progress.setVisible(value<100)
    def loading_changed(self,info):
        status=info.status();name=getattr(status,'name',str(status))
        if name=='Failed':self.progress.hide();self.status.setText('网页加载失败，可点击刷新重试');self.status.show()
        elif name=='Started':self.status.hide();self.progress.setValue(0);self.progress.show()
        elif name=='Succeeded':self.progress.hide();self.status.hide();self.back.setEnabled(self.view.canGoBack())
        elif name=='Stopped':self.progress.hide()
    def hideEvent(self,event):self.view.stop();super().hideEvent(event)


def run_native_check(output):
    """Frozen-runtime check: real WebView2 DOM, no visible windows or network."""
    import json,tempfile,time
    from PySide6.QtWidgets import QApplication,QVBoxLayout
    from ..paths import LAUNCHER_VERSION
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    profile=tempfile.mkdtemp(prefix='onion-webcheck-');os.environ['WEBVIEW2_USER_DATA_FOLDER']=profile
    result={'result':'fail','version':LAUNCHER_VERSION,'visible_windows':False}
    try:
        initialize_webview()
        from PySide6.QtWebView import QWebView
        app=QApplication.instance() or QApplication([]);root=QWidget();root.resize(800,600)
        view=QWebView();container=QWidget.createWindowContainer(view,root);QVBoxLayout(root).addWidget(container)
        root.winId();container.winId();view.create();states=[]
        view.loadingChanged.connect(lambda info:states.append(info.status().name))
        def wait(predicate):
            end=time.monotonic()+25
            while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
            assert predicate(),'WebView2 did not respond'
        view.loadHtml('<html><head><title>Onion THUnion WebView2 Check</title></head><body>Native web tools</body></html>')
        wait(lambda:'Succeeded' in states or 'Failed' in states);assert states[-1]=='Succeeded',states
        titles=[];view.runJavaScript('document.title',lambda title:titles.append(title));wait(lambda:bool(titles))
        assert titles[-1]=='Onion THUnion WebView2 Check'
        assert not root.isVisible() and not container.isVisible()
        result.update({'result':'pass','native_webview2_dom':True,'embedded_window':True})
        view.stop();view.destroy();root.close();app.processEvents()
    except Exception as error:result['error']=str(error)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['result']=='pass' else 1
