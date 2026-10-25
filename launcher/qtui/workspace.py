"""Instance selection and management keep every action bound to one instance."""
from .lists import FlatTreeWidget as QTreeWidget

from PySide6.QtCore import Qt,QPoint,QRectF,QSize,QEvent
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QFontMetrics
from PySide6.QtWidgets import QWidget,QDialog,QLineEdit,QTreeWidgetItem,QStackedWidget,QFormLayout,QMessageBox,QStyledItemDelegate,QStyle
from .widgets import Page,Card,ContentRow,column,row,label,button,clear,icon,control_accent
from .theme import paint_color,surface_opacity,config_for,contrasting_accent,appearance_values,effective_accent,corner,text_size,row_height,preference


class InstanceChoiceDelegate(QStyledItemDelegate):
    def __init__(self,picker):super().__init__(picker.tree);self.picker=picker

    def sizeHint(self,option,index):return QSize(320,row_height(self.picker,64))

    def paint(self,painter,option,index):
        picker=self.picker;vid=index.data(Qt.ItemDataRole.UserRole)
        current=vid==picker.launcher.selected_version
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(2,2,-2,-2);accent=QColor(control_accent(picker));factor=surface_opacity(config_for(picker))
        if current or option.state & (QStyle.StateFlag.State_Selected|QStyle.StateFlag.State_MouseOver):
            fill=QColor(accent);fill.setAlpha(round((42 if current else 22)*factor))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(fill);painter.drawRoundedRect(rect,corner(picker,10),corner(picker,10))
        badge=QRectF(rect.left()+12,rect.center().y()-18,36,36)
        tint=QColor(accent);tint.setAlpha(round(25*factor));painter.setBrush(tint);painter.setPen(Qt.PenStyle.NoPen);painter.drawRoundedRect(badge,9,9)
        icon('package',paint_color(picker,'icon')).paint(painter,int(badge.x()+8),int(badge.y()+8),20,20)
        x=rect.left()+60;width=max(0,int(rect.width()-x+rect.left()-36))
        bold=appearance_values(config_for(picker))['bold_text']
        font=QFont(picker.font());font.setPixelSize(text_size(picker,14));font.setWeight(QFont.Weight.DemiBold if current or bold else QFont.Weight.Normal)
        height=QFontMetrics(font).height()+2;detail_height=text_size(picker,12)+6
        text_top=rect.top()+(rect.height()-height-detail_height-2)/2
        painter.setFont(font);painter.setPen(paint_color(picker,'text',text=True))
        painter.drawText(QRectF(x,text_top,width,height),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(index.data() or '',Qt.TextElideMode.ElideRight,width))
        font.setPixelSize(text_size(picker,12));font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal);painter.setFont(font);painter.setPen(paint_color(picker,'muted',text=True))
        painter.drawText(QRectF(x,text_top+height+2,width,detail_height),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(index.data(Qt.ItemDataRole.UserRole+1) or '',Qt.TextElideMode.ElideRight,width))
        if current:
            marker=QColor(contrasting_accent(accent.name(),appearance_values(config_for(picker))['color_mode']))
            painter.setPen(QPen(marker,1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            right=rect.right()-14;y=rect.center().y();painter.drawLine(QPoint(int(right-8),int(y)),QPoint(int(right-5),int(y+3)));painter.drawLine(QPoint(int(right-5),int(y+3)),QPoint(int(right+1),int(y-4)))
        painter.restore()


class InstancePicker(QDialog):
    def __init__(self,launcher):
        super().__init__(launcher,Qt.WindowType.Popup|Qt.WindowType.FramelessWindowHint);self.launcher=launcher;self.resize(400,420)
        self.setObjectName('instancePicker');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay,True)
        body=column(self,14,10);heading=row();heading.addWidget(label('选择实例','heading'),1);self.count=label('','muted');heading.addWidget(self.count);body.addLayout(heading)
        self.query=QLineEdit();self.query.setPlaceholderText('搜索实例');self.query.setClearButtonEnabled(True);self.query.addAction(icon('search',paint_color(self,'icon')),QLineEdit.ActionPosition.LeadingPosition);body.addWidget(self.query)
        from .choices import ChoiceComboBox
        from ..game_libraries import GameLibraries
        from ..storage import directory_key
        self.library_choice=ChoiceComboBox()
        for entry in launcher.game_libraries.entries():self.library_choice.addItem(GameLibraries.title(entry),entry['path'])
        for index in range(self.library_choice.count()):
            if directory_key(self.library_choice.itemData(index))==directory_key(launcher.repo.game_dir):self.library_choice.setCurrentIndex(index)
        self.library_choice.setAccessibleName('游戏文件夹');self.library_choice.setToolTip(str(launcher.repo.game_dir));body.insertWidget(1,self.library_choice)
        def switch_library(index):
            path=self.library_choice.itemData(index)
            if path:self.accept();launcher.switch_game_library(path)
        self.library_choice.currentIndexChanged.connect(switch_library)
        self.tree=QTreeWidget();self.tree.setObjectName('instancePickerList');self.tree.setHeaderHidden(True);self.tree.setRootIsDecorated(False);self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True);self.tree.setMouseTracking(True);self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setItemDelegate(InstanceChoiceDelegate(self));body.addWidget(self.tree,1)
        self.empty=label('没有匹配的实例','muted');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);body.addWidget(self.empty)
        body.addWidget(button('管理实例',self.open_list,'soft','grid'))
        self.query.textChanged.connect(self.filter);self.tree.itemClicked.connect(self.choose)
        self.query.returnPressed.connect(lambda:self.choose(self.tree.currentItem()) if self.tree.currentItem() else None);self.filter()
        self.query.installEventFilter(self);self.tree.installEventFilter(self)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill=paint_color(self,'surface');factor=surface_opacity(config_for(self));fill.setAlpha(round(250*factor))
        border=paint_color(self,'icon');border.setAlpha(round(55*factor));p.setPen(QPen(border,1));p.setBrush(fill)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),corner(self,16),corner(self,16))

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.KeyPress:
            if event.key()==Qt.Key.Key_Down and watched is self.query and self.tree.topLevelItemCount():
                self.tree.setFocus();self.tree.setCurrentItem(self.tree.topLevelItem(0));return True
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and watched is self.tree:
                self.choose(self.tree.currentItem());return True
        return super().eventFilter(watched,event)

    def filter(self):
        w=self.launcher;query=self.query.text().strip().lower();self.tree.clear()
        for vid in sorted(w.versions,key=lambda v:(not w.instances.get(v).favorite,w.instances.display_name(v).casefold(),v.casefold())):
            if query not in (vid+' '+w.instances.display_name(vid)+' '+w.instances.get(vid).group+' '+' '.join(w.instances.get(vid).tags)).lower():continue
            kind=w.kinds.get(vid,'原版');version=vid[:-(len(kind)+1)] if vid.casefold().endswith('-'+kind.casefold()) else vid
            detail=' · '.join(part for part in (version,kind,w.instances.get(vid).group,*w.instances.get(vid).tags) if part)
            item=QTreeWidgetItem([('★ ' if w.instances.get(vid).favorite else '')+w.instances.display_name(vid)]);item.setData(0,Qt.ItemDataRole.UserRole,vid);item.setData(0,Qt.ItemDataRole.UserRole+1,detail)
            item.setToolTip(0,w.instances.display_name(vid)+'\n'+vid+' · '+kind);self.tree.addTopLevelItem(item)
            if vid==w.selected_version:self.tree.setCurrentItem(item)
        count=self.tree.topLevelItemCount();self.count.setText(str(count));self.empty.setVisible(not count);self.tree.setVisible(bool(count))
        if count and self.tree.currentItem() is None:self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def choose(self,item,column=0):
        if item and self.launcher.set_selected(item.data(0,Qt.ItemDataRole.UserRole)):self.accept()

    def open_list(self):self.accept();self.launcher.navigate('versions')

    def show_above(self,anchor):
        screen=anchor.screen().availableGeometry();height=210+max(1,min(5,self.tree.topLevelItemCount()))*64
        self.resize(min(400,screen.width()-16),min(height,510,screen.height()-32))
        point=anchor.mapToGlobal(QPoint(anchor.width()-self.width(),-self.height()-10))
        self.move(max(screen.left()+8,min(point.x(),screen.right()-self.width()-8)),max(screen.top()+8,min(point.y(),screen.bottom()-self.height()-8)))
        self.show();self.query.setFocus()
        if self.tree.currentItem():self.tree.scrollToItem(self.tree.currentItem())


class InstanceWorkspace(QWidget):
    def __init__(self,launcher,vid):
        super().__init__();self.launcher=launcher;self.vid=vid;self.pages={};self.buttons={}
        body=column(self,12,0);self.stack=QStackedWidget();body.addWidget(self.stack,1)
        from .settings import SettingsEditor
        self.editor=SettingsEditor(launcher,vid,flat=True);self.pages['game']=self.editor;self.stack.addWidget(self.editor)

    def open_tab(self,key):
        w=self.launcher;w.instance_tab=key
        for name,item in self.buttons.items():item.setChecked(name==key)
        if key not in self.pages:
            if key=='screenshots':
                self.pages[key]=QWidget();self.pages[key].body=column(self.pages[key],0,0)
            else:self.pages[key]=Page()
            self.stack.addWidget(self.pages[key])
        self.stack.setCurrentWidget(self.pages[key])
        if key=='game':self.editor.refresh_inherited();return
        w.instance_content=self.pages[key]
        if key in ('mods','resourcepacks','shaderpacks'):w.build_mods(key)
        elif key=='worlds':w.build_worlds()
        elif key in ('schematics','screenshots'):
            from .file_library import InstanceFiles
            page=self.pages[key]
            if not hasattr(page,'file_browser'):
                page.file_browser=InstanceFiles(w,self.vid,key=='screenshots');page.body.addWidget(page.file_browser)
            else:page.file_browser.reload()
        elif key=='logs':w.build_logs()
        elif key=='info':self.build_info()
        elif key=='auto':self.build_auto()

    def build_auto(self):
        w=self.launcher;page=self.pages['auto'];clear(page.body)
        from ..components import component_info
        from ..version import VersionError
        try:game,current,version=component_info(w.repo,self.vid)
        except (OSError,ValueError,VersionError) as error:page.body.addWidget(label(str(error),'muted',True));return
        page.body.setSpacing(0);page.body.addWidget(ContentRow('Minecraft',game,'package'))
        for key,title in [('fabric','Fabric'),('quilt','Quilt'),('forge','Forge'),('neoforge','NeoForge'),('optifine','OptiFine')]:
            supported=key in ('fabric','quilt') and (not current or current==key)
            detail=version if current==key else '与 '+current.title()+' 不兼容' if current else '未安装'
            if not supported and (not current or current==key):detail+=' · 暂不支持原位安装'
            item=ContentRow(title,detail,'package')
            if supported:
                def choose(kind=key):
                    from .component_versions import ComponentVersions
                    w.show_subpage(ComponentVersions(w,self.vid,kind))
                item.line.addWidget(button('更换版本' if current==key else '安装',choose,'soft','download'))
            page.body.addWidget(item)

    def build_info(self):
        w=self.launcher;page=self.pages['info'];clear(page.body);meta=w.instances.get(self.vid)
        card=Card('实例信息');fields={};form=QFormLayout()
        for key,title,value in [('name','显示名称',meta.name),('group','分组',meta.group),('tags','标签（逗号分隔）',', '.join(meta.tags)),('notes','备注',meta.notes)]:
            edit=QLineEdit(value);edit.setPlaceholderText(self.vid if key=='name' else '可选');fields[key]=edit;form.addRow(title,edit)
        card.body.addLayout(form)
        from PySide6.QtWidgets import QCheckBox
        favorite=QCheckBox('收藏此实例');favorite.setChecked(meta.favorite);card.body.addWidget(favorite)
        def save():
            w.instances.update(self.vid,favorite=favorite.isChecked(),**{key:edit.text().strip() for key,edit in fields.items()});w.update_selection();w.reload_versions(refresh_page=False);w.status.setText('实例信息已保存')
        card.body.addWidget(button('保存实例信息',save,'primary'));page.body.addWidget(card)
        card=Card('维护与恢复','文件移除后进入恢复中心，可在原位置不存在时恢复。')
        for title,callback in [('启动前环境体检',lambda:w.preflight(self.vid)),('校验游戏文件',lambda:w.verify_version(self.vid)),('导出整合包',lambda:w.export_modpack(self.vid)),('恢复中心',w.recovery),('移除当前实例',lambda:w.delete_version(self.vid))]:card.body.addWidget(button(title,callback,'soft'))
        page.body.addWidget(card)
