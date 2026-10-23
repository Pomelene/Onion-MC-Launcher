"""Asynchronous, full-viewport biome atlas. Gestures never wait for generation."""
import math
from array import array
from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import Qt,Signal,QPointF,QRectF,QTimer,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QImage,QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QLineEdit,QCheckBox,QFileDialog,QApplication,QScrollArea,QAbstractSpinBox
from shiboken6 import isValid
from .widgets import column,row,label,button,InlineSpinBox,control_accent
from .choices import ChoiceComboBox,ActionMenu
from .theme import paint_color
from .motion import motion_enabled
from ..map_view import Viewport,tile_cells,biome_name,biome_color
from ..seedmap import VERSIONS,STRUCTURES,parse_seed,generate,structure_positions


BADGES=list(zip(STRUCTURES,'村沙丛巫海林哨古堡垒末试营',
    ('#b88f57','#c28e4c','#55916b','#83719c','#508d99','#687a50','#9d7158',
     '#537c89','#a56c6c','#a2856e','#958662','#9b7eaa','#8a8159')))


def raster_tile(data):
    colors={key:biome_color(value) for key,value in data.legend.items()}
    rgb=b''.join(colors[value] for value in data.ids)
    image=QImage(rgb,data.size,data.size,data.size*3,QImage.Format.Format_RGB888).copy()
    return image,array('h',data.ids),data.legend,data.origin,data.scale,data.size


class MapCanvas(QWidget):
    moved=Signal();hovered=Signal(str);selected=Signal(str,int,int)
    def __init__(self):
        super().__init__();self.view=Viewport();self.tiles=OrderedDict();self.markers=[]
        self.enabled_layers=set(STRUCTURES);self.grid=False;self.active=False;self.selection=None;self.show_markers=True
        self.drag=None;self.drag_distance=0;self.hit_regions=[];self.image=QImage()
        self.setMinimumSize(320,300);self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor);self.setAccessibleName('种子地图，拖动平移，滚轮缩放，单击查看坐标')
        self.animation=QVariantAnimation(self);self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic);self.animation.valueChanged.connect(self.zoom_frame)
        self.animation.finished.connect(self.moved);self.anchor=QPointF();self.zoom_target=4

    def set_data(self,data):
        # Frozen self-check injects one isolated tile without starting background work.
        self.tiles.clear();self.add_tile(('fixture',),raster_tile(data));self.markers=data.structures
        self.view=Viewport(data.origin[0]+data.size*data.scale/2,data.origin[1]+data.size*data.scale/2,data.scale)
        self.active=True;self.update()

    def add_tile(self,key,tile):
        self.tiles[key]=tile;self.tiles.move_to_end(key)
        # RGB images + 16-bit biome IDs have a bounded combined cache.
        while sum(t[0].sizeInBytes()+len(t[1])*2 for t in self.tiles.values())>32*1024*1024:self.tiles.popitem(last=False)
        self.image=tile[0];self.update()

    def screen(self,x,z):return QPointF(*self.view.screen(x,z,self.width(),self.height()))
    def world(self,point):return self.view.world(point.x(),point.y(),self.width(),self.height())

    def biome_at(self,x,z):
        for tile in sorted(self.tiles.values(),key=lambda t:t[4]):
            _,ids,legend,(ox,oz),scale,size=tile
            px,pz=math.floor((x-ox)/scale),math.floor((z-oz)/scale)
            if 0<=px<size and 0<=pz<size:return biome_name(legend[ids[pz*size+px]])
        return '地图计算中'

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),paint_color(self,'base'))
        if not self.active:
            p.setPen(paint_color(self,'muted',text=True))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'输入世界种子，探索生物群系与结构');return
        for image,ids,legend,(x,z),scale,size in sorted(self.tiles.values(),key=lambda t:-t[4]):
            point=self.screen(x,z);side=size*scale/self.view.blocks_per_pixel
            target=QRectF(point.x(),point.y(),side,side)
            if target.intersects(QRectF(self.rect())):p.drawImage(target,image)
        if self.grid:
            spacing=16
            while spacing/self.view.blocks_per_pixel<64:spacing*=4
            left,top,right,bottom=self.view.bounds(self.width(),self.height())
            p.setPen(QPen(QColor(25,35,44,55),1))
            for x in range(math.floor(left/spacing)*spacing,math.ceil(right/spacing)*spacing,spacing):
                sx=self.screen(x,0).x();p.drawLine(QPointF(sx,0),QPointF(sx,self.height()))
            for z in range(math.floor(top/spacing)*spacing,math.ceil(bottom/spacing)*spacing,spacing):
                sy=self.screen(0,z).y();p.drawLine(QPointF(0,sy),QPointF(self.width(),sy))
        self.hit_regions=[];occupied=[]
        markers=sorted(self.markers if self.show_markers else [],key=lambda item:(item==self.selection,(item[1]-self.view.x)**2+(item[2]-self.view.z)**2))
        for name,x,z in markers:
            if name not in self.enabled_layers:continue
            point=self.screen(x,z);rect=QRectF(point.x()-11,point.y()-13,22,26)
            if not rect.intersects(QRectF(self.rect())):continue
            _,glyph,color=next(item for item in BADGES if item[0]==name)
            active=(name,x,z)==self.selection
            p.setPen(QPen(QColor(255,255,255,255 if active else 200),2 if active else 1))
            p.setBrush(QColor(color));p.drawRoundedRect(rect,7,7)
            p.setPen(QColor('white'));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,glyph)
            self.hit_regions.append((rect,(name,x,z)))
            if self.view.blocks_per_pixel<=2 or active:
                width=p.fontMetrics().horizontalAdvance(name)+14
                text_rect=QRectF(point.x()+15,point.y()-12,width,24)
                if active or not any(text_rect.intersects(r) for r in occupied):
                    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(24,25,36,220));p.drawRoundedRect(text_rect,6,6)
                    p.setPen(QColor('white'));p.drawText(text_rect,Qt.AlignmentFlag.AlignCenter,name);occupied.append(text_rect)
        if self.selection:
            point=self.screen(*self.selection[1:]);p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(control_accent(self)),2));p.drawEllipse(point,19,19)
        p.setPen(QPen(QColor(255,255,255,170),1));center=QPointF(self.width()/2,self.height()/2)
        p.drawLine(center+QPointF(-5,0),center+QPointF(5,0));p.drawLine(center+QPointF(0,-5),center+QPointF(0,5))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(24,25,36,210))
        p.drawRoundedRect(QRectF(self.width()-47,12,34,36),10,10)
        p.setPen(QColor('white'));p.drawText(QRectF(self.width()-47,12,34,36),Qt.AlignmentFlag.AlignCenter,'N ↑')
        distance=10**math.floor(math.log10(max(1,110*self.view.blocks_per_pixel)))
        for multiplier in (5,2,1):
            if distance*multiplier/self.view.blocks_per_pixel<=150:distance*=multiplier;break
        length=distance/self.view.blocks_per_pixel
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(24,25,36,210));p.drawRoundedRect(QRectF(12,self.height()-49,max(95,length+24),37),8,8)
        p.setPen(QPen(QColor('white'),2));y=self.height()-22
        p.drawLine(QPointF(24,y),QPointF(24+length,y));p.drawLine(QPointF(24,y-3),QPointF(24,y+3));p.drawLine(QPointF(24+length,y-3),QPointF(24+length,y+3))
        p.drawText(QRectF(24,y-23,max(70,length),20),f'{distance:,} 方块')

    def resizeEvent(self,event):super().resizeEvent(event);self.moved.emit()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.active:
            self.animation.stop();self.drag=event.position();self.drag_distance=0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
    def mouseMoveEvent(self,event):
        if not self.active:return
        if self.drag is not None:
            if not event.buttons()&Qt.MouseButton.LeftButton:self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                delta=event.position()-self.drag;self.drag=event.position();self.drag_distance+=abs(delta.x())+abs(delta.y())
                self.view.pan(delta.x(),delta.y());self.update();self.moved.emit()
        x,z=self.world(event.position());self.hovered.emit(f'X {math.floor(x):,}   Z {math.floor(z):,}   ·   {self.biome_at(x,z)}')
    def mouseReleaseEvent(self,event):
        if self.drag is None or event.button()!=Qt.MouseButton.LeftButton:return
        self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.drag_distance<5:
            marker=next((item for rect,item in reversed(self.hit_regions) if rect.contains(event.position())),None)
            x,z=self.world(event.position());self.selection=marker or (self.biome_at(x,z),math.floor(x),math.floor(z))
            self.selected.emit(*self.selection);self.update()
        self.moved.emit()
    def hideEvent(self,event):
        self.animation.stop();self.drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor);super().hideEvent(event)
    def zoom_to(self,bpp,point=None):
        if not self.active:return
        self.animation.stop();self.anchor=point or QPointF(self.width()/2,self.height()/2)
        self.zoom_target=max(.125,min(256,bpp));self.animation.setStartValue(math.log2(self.view.blocks_per_pixel))
        self.animation.setEndValue(math.log2(self.zoom_target))
        if motion_enabled(self):self.animation.start()
        else:self.zoom_frame(math.log2(self.zoom_target));self.moved.emit()
    def zoom_frame(self,value):
        self.view.zoom_at(2**float(value),self.anchor.x(),self.anchor.y(),self.width(),self.height());self.update()
    def wheelEvent(self,event):
        if self.active:
            delta=event.pixelDelta().y()/180 if not event.pixelDelta().isNull() else event.angleDelta().y()/240
            base=self.zoom_target if self.animation.state()==self.animation.State.Running else self.view.blocks_per_pixel
            self.zoom_to(base*2**(-delta),event.position());event.accept()
    def contextMenuEvent(self,event):
        if not self.active:return
        x,z=self.world(QPointF(event.pos()));x,z=math.floor(x),math.floor(z)
        menu=ActionMenu(self)
        menu.addAction(f'复制坐标 · {x}, {z}',lambda:QApplication.clipboard().setText(f'X {x} Z {z}'))
        menu.addAction('复制传送指令',lambda:QApplication.clipboard().setText(f'/tp @s {x} ~ {z}'))
        menu.exec(event.globalPos())


class SeedMap(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.context=None;self.epoch=0;self.inflight=set();self.wanted=[]
        self.failed_tiles=set();self.structure_job=False;self.structure_coverage=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(130);self.timer.timeout.connect(self.refresh_view)
        body=column(self,0,10);top=row(spacing=8)
        self.seed=QLineEdit();self.seed.setPlaceholderText('世界种子 · 数字或文本');top.addWidget(self.seed,1)
        self.version=ChoiceComboBox();self.version.addItems(VERSIONS);top.addWidget(self.version)
        self.dimension=ChoiceComboBox()
        for title,value in [('主世界',0),('下界',-1),('末地',1)]:self.dimension.addItem(title,value)
        top.addWidget(self.dimension);self.go=button('探索地图',self.render_map,'primary','world');top.addWidget(self.go)
        top.addWidget(button('读取存档',self.read_world,glyph='folder'));body.addLayout(top)
        controls=row(spacing=8);self.coords=[]
        for name,lo,hi,value in [('X',-29_000_000,29_000_000,0),('Z',-29_000_000,29_000_000,0),('Y',-64,320,64)]:
            controls.addWidget(label(name,'muted'));spin=InlineSpinBox();spin.setRange(lo,hi);spin.setValue(value)
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setMinimumWidth(74);spin.setMaximumWidth(125);controls.addWidget(spin);self.coords.append(spin)
        controls.addWidget(button('定位',self.locate,glyph='search'));controls.addStretch()
        self.grid=QCheckBox('网格');controls.addWidget(self.grid)
        self.layer_toggle=button('图层',self.toggle_layers,glyph='list');controls.addWidget(self.layer_toggle)
        controls.addWidget(button('−',lambda:self.canvas.zoom_to(self.canvas.view.blocks_per_pixel*2)))
        controls.addWidget(button('+',lambda:self.canvas.zoom_to(self.canvas.view.blocks_per_pixel/2)))
        controls.addWidget(button('原点',lambda:self.pan(-self.canvas.view.x,-self.canvas.view.z)))
        body.addLayout(controls)
        content=row(spacing=10);body.addLayout(content,1)
        self.layers=QWidget();self.layers.setFixedWidth(176);left=column(self.layers,0,8)
        left.addWidget(label('结构图层','heading'));toggles=row(spacing=4)
        toggles.addWidget(button('全选',lambda:self.set_layers(True)));toggles.addWidget(button('清空',lambda:self.set_layers(False)));left.addLayout(toggles)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(scroll.Shape.NoFrame)
        list_widget=QWidget();listing=column(list_widget,0,4);self.checks={}
        for name,glyph,color in BADGES:
            check=QCheckBox(name);check.setChecked(name not in ('试炼密室','废弃营地'));check.setMinimumHeight(29)
            check.setToolTip('预测位置，未校验全部地形条件');check.toggled.connect(self.update_layers)
            listing.addWidget(check);self.checks[name]=check
        listing.addStretch();scroll.setWidget(list_widget);left.addWidget(scroll,1)
        self.detail=label('单击地图查看位置','muted',True);left.addWidget(self.detail)
        self.copy=button('复制坐标',self.copy_selection,glyph='copy');self.copy.setEnabled(False);left.addWidget(self.copy)
        self.tp=button('复制传送指令',lambda:self.copy_selection(True));self.tp.setEnabled(False);left.addWidget(self.tp)
        content.addWidget(self.layers);self.canvas=MapCanvas();content.addWidget(self.canvas,1)
        footer=row(spacing=12);self.status=label('Java 版 · 拖动平移 / 滚轮缩放','muted');footer.addWidget(self.status,1)
        self.progress=label('','muted');footer.addWidget(self.progress);body.addLayout(footer)
        self.progress.setToolTip('结构为生成规则预测位置；不包含模组结构，尚未校验全部地形条件')
        self.canvas.moved.connect(self.view_moved);self.canvas.hovered.connect(self.status.setText)
        self.canvas.selected.connect(self.select);self.grid.toggled.connect(self.change_grid);self.seed.returnPressed.connect(self.render_map)
        self.coords[2].editingFinished.connect(self.locate)
        self.update_layers()

    @property
    def busy(self):return bool(self.inflight or self.structure_job or self.timer.isActive() or self.wanted)
    def change_grid(self,checked):self.canvas.grid=checked;self.canvas.update()
    def toggle_layers(self):self.layers.setVisible(self.layers.isHidden());self.timer.start()
    def set_layers(self,checked):
        for check in self.checks.values():check.blockSignals(True);check.setChecked(checked);check.blockSignals(False)
        self.update_layers()
    def update_layers(self):
        if not hasattr(self,'canvas'):return
        self.canvas.enabled_layers={name for name,check in self.checks.items() if check.isChecked()};self.canvas.update()
    def select(self,name,x,z):
        self.detail.setText(f'{name}\nX {x:,}   Z {z:,}');self.copy.setEnabled(True);self.tp.setEnabled(True)
        if self.layers.isHidden():self.layers.show()
    def copy_selection(self,tp=False):
        if not self.canvas.selection:return
        _,x,z=self.canvas.selection;QApplication.clipboard().setText(f'/tp @s {x} ~ {z}' if tp else f'X {x} Z {z}')
    def locate(self):
        if self.context is None:return self.render_map()
        try:desired=(parse_seed(self.seed.text()),self.version.currentText(),self.dimension.currentData(),self.coords[2].value())
        except ValueError as error:self.status.setText(str(error));return
        if desired!=self.context:return self.render_map()
        self.canvas.animation.stop();self.canvas.view.x=self.coords[0].value();self.canvas.view.z=self.coords[1].value()
        self.canvas.update();self.refresh_view()
    def pan(self,x,z):
        self.canvas.animation.stop();self.canvas.view.pan(-x/self.canvas.view.blocks_per_pixel,-z/self.canvas.view.blocks_per_pixel)
        self.canvas.update();self.view_moved();self.refresh_view()
    def view_moved(self):
        self.coords[0].setValue(round(self.canvas.view.x));self.coords[1].setValue(round(self.canvas.view.z))
        if self.context:self.timer.start()
    def render_map(self):
        try:context=(parse_seed(self.seed.text()),self.version.currentText(),self.dimension.currentData(),self.coords[2].value())
        except ValueError as error:self.status.setText(str(error));return
        self.failed_tiles.clear()
        if context!=self.context:
            self.context=context;self.epoch+=1;self.canvas.tiles.clear();self.canvas.markers=[];self.canvas.selection=None
            self.failed_tiles.clear();self.structure_coverage=None;self.copy.setEnabled(False);self.tp.setEnabled(False)
            self.detail.setText('单击地图查看位置')
            for name,check in self.checks.items():
                dimension=-1 if name in ('下界要塞','堡垒遗迹') else 1 if name=='末地城' else 0
                check.setVisible(dimension==context[2])
        self.canvas.animation.stop();self.canvas.view.x=self.coords[0].value();self.canvas.view.z=self.coords[1].value()
        self.canvas.active=True;self.canvas.update();self.refresh_view()
    def refresh_view(self):
        self.timer.stop()
        if self.context is None:return
        scale,cells=tile_cells(self.canvas.view,self.canvas.width(),self.canvas.height())
        epoch=self.epoch;cells=[(x,z) for x,z in cells if max(abs(x+scale*128),abs(z+scale*128))<=29_000_000]
        # Same world-aligned footprints: quick coarse coverage, then fine detail.
        previews=[(epoch,scale,x,z,64) for x,z in cells] if scale<256 else []
        self.wanted=previews+[(epoch,scale,x,z,256) for x,z in cells]
        for key in self.wanted:
            if key in self.canvas.tiles:self.canvas.tiles.move_to_end(key)
        self.pump_tiles();self.query_structures()
    def pump_tiles(self):
        if not isValid(self):return
        missing=[key for key in self.wanted if key not in self.canvas.tiles and key not in self.inflight and key not in self.failed_tiles]
        while missing and len(self.inflight)<2:
            key=missing.pop(0);self.inflight.add(key);epoch,scale,x,z,pixels=key;seed,version,dimension,y=self.context
            def work(job,seed=seed,version=version,dimension=dimension,y=y,scale=scale,x=x,z=z,pixels=pixels):
                return raster_tile(generate(seed,version,dimension,x+scale*128,z+scale*128,scale*(256//pixels),y,pixels,False))
            def done(tile,key=key):
                if not isValid(self):return
                self.inflight.discard(key)
                if key[0]==self.epoch:self.canvas.add_tile(key,tile)
                self.pump_tiles()
            def failed(error,key=key):
                if not isValid(self):return
                self.inflight.discard(key)
                if key[0]==self.epoch:self.failed_tiles.add(key);self.status.setText(str(error))
                self.pump_tiles()
            self.owner.tasks.submit(work,done,failed)
        remaining=sum(key not in self.canvas.tiles and key not in self.failed_tiles for key in self.wanted)
        self.progress.setText(f'补齐地图 · {remaining} 块' if remaining else '本地地图 · 结构预测')
        if not remaining:self.wanted=[]
    def query_structures(self):
        bounds=self.canvas.view.bounds(self.canvas.width(),self.canvas.height())
        span=math.ceil(max(bounds[2]-bounds[0],bounds[3]-bounds[1])*1.3)
        self.canvas.show_markers=span<=16000;self.canvas.update()
        if span>16000:
            self.progress.setText('放大地图以查看结构');return
        if self.structure_coverage and self.structure_coverage[0]==self.epoch:
            _,x,z,size=self.structure_coverage
            if x<=bounds[0] and z<=bounds[1] and x+size>=bounds[2] and z+size>=bounds[3]:return
        if self.structure_job:return
        span=max(1024,span);x=math.floor(self.canvas.view.x-span/2);z=math.floor(self.canvas.view.z-span/2)
        if max(abs(x),abs(z))>29_000_000:return
        epoch=self.epoch;seed,version,dimension,y=self.context;self.structure_job=True
        def done(markers):
            if not isValid(self):return
            self.structure_job=False
            if epoch==self.epoch:
                self.canvas.markers=markers;self.structure_coverage=(epoch,x,z,span);self.canvas.update()
            self.query_structures()
        def failed(error):
            if isValid(self):self.structure_job=False;self.status.setText(str(error))
        self.owner.tasks.submit(lambda job:structure_positions(seed,version,dimension,x,z,span),done,failed)
    def read_world(self):
        path,_=QFileDialog.getOpenFileName(self,'选择存档 level.dat','','世界数据 (level.dat)')
        if not path:return
        from ..worlds import read_level_dat
        try:
            data=read_level_dat(Path(path));settings=data.get('WorldGenSettings',{})
            seed=settings.get('seed') if isinstance(settings,dict) else None
            if seed is None:seed=data.get('RandomSeed')
            if not isinstance(seed,int):raise ValueError('未能读取世界种子')
            self.seed.setText(str(seed));self.status.setText('已读取种子，请核对版本后探索地图')
        except Exception as error:self.status.setText(str(error))
