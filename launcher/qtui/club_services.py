"""THUnion service categories describe each tool before opening its web page."""
from PySide6.QtCore import Qt,QObject,Signal,QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget,QStackedWidget,QDialog
from shiboken6 import isValid
from .widgets import Page,Card,Empty,column,row,label,button,clear,NavigationItem
from .theme import paint_color
from ..club_services import CONFIRMATION,read_catalog,sync_catalog


class ServiceConfirmation(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('THUnion 社团服务');self.setFixedWidth(480)
        body=column(self,24,18)
        body.addWidget(label('访问社团服务','heading'))
        notice=Card('THUnion · 清华联盟工坊',CONFIRMATION);body.addWidget(notice)
        body.addWidget(label('本次运行仅确认一次，服务目录同步后保存在本地。','muted',True))
        actions=row();actions.addStretch()
        cancel=button('暂不进入',self.reject,'soft');proceed=button('确认并进入',self.accept,'primary')
        for control in (cancel,proceed):control.setMinimumWidth(112);control.setFixedHeight(40);actions.addWidget(control)
        cancel.setDefault(True);cancel.setFocus();body.addLayout(actions)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(paint_color(self,'base'))
        painter.drawRoundedRect(QRectF(self.rect()),12,12)


class ServiceSession(QObject):
    """Owned by the main window so page reconstruction cannot reset consent or sync."""
    changed=Signal()

    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.confirmed=False;self.started=False;self.loading=False
        self.catalog=None;self.error='';self.path=owner.root/'.onion/services/thunion/webapp.json'

    def start(self):
        if self.started:return
        self.started=True;self.loading=True
        def done(catalog):
            self.catalog=catalog;self.loading=False;self.error='';self.changed.emit()
        def failed(error):
            self.loading=False;self.error=str(error)
            try:self.catalog=read_catalog(self.path)
            except (OSError,ValueError):self.catalog=None
            self.changed.emit()
        self.owner.tasks.submit(lambda job:sync_catalog(self.path),done,failed)

    def read_local(self):
        if self.loading:return
        try:self.catalog=read_catalog(self.path)
        except (OSError,ValueError):
            if self.catalog is None:self.error='没有可用的本地服务目录，请下次启动后重新同步。'


class ClubServices(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.catalog=None;self.browser=None;self.web_factory=None;self.expanded=False;self.web_layout=False
        if not hasattr(owner,'club_service_session'):owner.club_service_session=ServiceSession(owner)
        self.session=owner.club_service_session;self.session.changed.connect(self.show_catalog)
        body=column(self,0,12);self.heading=QWidget();heading=row(self.heading);heading.addWidget(label('社团服务','heading'),1)
        body.addWidget(self.heading)
        self.status=label('','muted',True);body.addWidget(self.status)
        self.stack=QStackedWidget();body.addWidget(self.stack,1)
        self.directory=QWidget();content=row(self.directory,0,18);self.stack.addWidget(self.directory)
        self.categories=QWidget();self.categories.setFixedWidth(170);self.category_list=column(self.categories,0,6);content.addWidget(self.categories)
        self.tools=Page();content.addWidget(self.tools,1);self.buttons=[]

    def enter(self):
        if not self.session.confirmed:
            if ServiceConfirmation(self.owner).exec()!=QDialog.DialogCode.Accepted:return False
            self.session.confirmed=True
        self.close_browser();self.session.start();self.session.read_local();self.show_catalog()
        return True

    def show_catalog(self):
        if not isValid(self):return
        self.catalog=self.session.catalog
        self.stack.setCurrentWidget(self.directory);clear(self.category_list);clear(self.tools.body)
        if self.session.loading:
            self.status.setText('正在同步社团服务目录…');self.tools.body.addWidget(Empty('正在读取目录','','world'))
        elif self.catalog:
            self.status.setText('同步失败，正在使用本地目录。'+self.session.error if self.session.error else '')
            self.render_categories()
        else:
            self.status.setText(self.session.error)
            self.tools.body.addWidget(Empty('暂无可用的服务目录','下次启动时会重新尝试同步','world'))

    def render_categories(self):
        clear(self.category_list);self.buttons=[]
        for category in self.catalog['categories']:
            item=NavigationItem(category['title'],'folder',lambda c=category:self.select_category(c))
            self.category_list.addWidget(item);self.buttons.append((item,category['id']))
        self.category_list.addStretch();self.select_category(self.catalog['categories'][0])
    def select_category(self,category):
        self.stack.setCurrentWidget(self.directory);clear(self.tools.body)
        for item,ident in self.buttons:item.setChecked(ident==category['id'])
        self.tools.body.addWidget(label(category['title'],'heading'))
        self.tools.body.addWidget(label(category['description'],'muted',True))
        for tool in category['tools']:
            card=Card(tool['title'],tool['description']);line=row()
            url=label(tool['url'],'muted',True);url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);line.addWidget(url,1)
            line.addWidget(button('打开',lambda t=tool:self.open_tool(t),'primary','world'));card.body.addLayout(line);self.tools.body.addWidget(card)
    def open_tool(self,tool):
        from .web_tools import WebTool
        self.close_browser()
        try:
            self.browser=WebTool(tool,self.return_to_catalog,self.web_factory,self.toggle_navigation);self.stack.addWidget(self.browser);self.stack.setCurrentWidget(self.browser)
            self.set_web_layout(True);self.set_expanded(True)
            self.owner.title.setText(tool['title'])
        except (ImportError,RuntimeError) as error:self.status.setText('内嵌浏览器不可用，请检查 WebView2 运行时或更新启动器：'+str(error))

    def set_web_layout(self,active):
        if active==self.web_layout:return
        self.web_layout=active;self.heading.setVisible(not active);self.status.setVisible(not active and bool(self.status.text()))
        self.layout().setSpacing(0 if active else 12)
        layout=self.owner.workshop.layout()
        if active:
            margins=layout.contentsMargins();self.saved_margins=(margins.left(),margins.top(),margins.right(),margins.bottom())
            layout.setContentsMargins(0,0,0,0)
        else:layout.setContentsMargins(*self.saved_margins)

    def set_expanded(self,expanded):
        self.expanded=expanded;self.owner.sidebar.setVisible(not expanded)
        if self.browser:self.browser.navigation.setText('显示导航' if expanded else '展开网页')

    def toggle_navigation(self):self.set_expanded(not self.expanded)
    def return_to_catalog(self):
        self.stack.setCurrentWidget(self.directory);self.close_browser();self.status.setText('');self.status.hide()
    def close_browser(self):
        if self.web_layout:
            self.set_expanded(False);self.set_web_layout(False)
            if self.owner.current_page=='tools':self.owner.title.setText(self.owner.page_title)
        if self.browser:
            self.browser.view.stop();self.stack.removeWidget(self.browser);self.browser.deleteLater();self.browser=None
    def hideEvent(self,event):
        self.close_browser();super().hideEvent(event)
