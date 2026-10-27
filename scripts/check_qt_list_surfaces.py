"""Raster checks for rounded list backings over bright wallpaper-like patterns."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QPainter,QColor,QImage
from PySide6.QtWidgets import QApplication,QWidget,QTreeWidgetItem,QVBoxLayout
from PySide6.QtTest import QTest
from launcher.qtui.lists import FlatTreeWidget,DETAIL_ROLE
from launcher.qtui.theme import appearance_style
from launcher.qtui.widgets import favorite_button,icon_button,configure_fonts


class Wallpaper(QWidget):
    def color_at(self,x,y):return QColor('#fff1cc' if (x//64+y//64)%2 else '#b18cf4')
    def paintEvent(self,event):
        painter=QPainter(self)
        for y in range(0,self.height(),64):
            for x in range(0,self.width(),64):painter.fillRect(x,y,64,64,self.color_at(x,y))


app=QApplication([]);configure_fonts(app);root=Wallpaper();root.config_obj={};layout=QVBoxLayout(root);layout.setContentsMargins(24,24,24,24)
tree=FlatTreeWidget();tree.entities(2);tree.setFixedSize(640,320);layout.addWidget(tree);root.resize(688,368)
for i in range(3):
    node=QTreeWidgetItem([f'实例 {i+1}','','']);node.setData(0,DETAIL_ROLE,'Minecraft 26.3 · Fabric');tree.addTopLevelItem(node)
    tree.setItemWidget(node,1,favorite_button(False,lambda _:None));tree.setItemWidget(node,2,icon_button('管理实例',lambda:None,'settings'))
tree.setCurrentItem(tree.topLevelItem(0));root.show();app.processEvents()
for mode in ('dark','light'):
    base=QColor('#121214' if mode=='dark' else '#ffffff')
    for radius in (0,10,24):
        for transparency in (0,30,90):
            root.config_obj.update(color_mode=mode,corner_radius=radius,ui_transparency=transparency)
            root.setStyleSheet(appearance_style('#cebafa',root.config_obj));QTest.qWait(15)
            QTest.mouseMove(root,QPoint(2,2));app.processEvents()
            captured=root.grab().toImage();point=tree.mapTo(root,QPoint(32,tree.height()-24))
            actual=captured.pixelColor(point);wall=root.color_at(point.x(),point.y());factor=1-transparency/100
            expected=[round(front*factor+back*(1-factor)) for front,back in zip(base.getRgb()[:3],wall.getRgb()[:3])]
            assert max(abs(a-b) for a,b in zip(actual.getRgb()[:3],expected))<=2,(mode,radius,transparency,actual.name(),expected)
            if radius:
                corner=tree.mapTo(root,QPoint(0,0));assert captured.pixelColor(corner)==root.color_at(corner.x(),corner.y()),(mode,radius,'corner')
            assert tree.viewport().pos().x()>=4 and tree.viewport().pos().y()>=4
            if radius==10 and transparency==0:captured.save(str(ROOT/'tmp'/f'list-surface-{mode}.png'))
        # Selected/hovered rows and action widgets stay inside the rounded panel.
        root.config_obj['ui_transparency']=0;root.setStyleSheet(appearance_style('#cebafa',root.config_obj));QTest.mouseMove(tree.viewport(),QPoint(3,3));app.processEvents()
        for scale in (1,1.5,2):
            image=QImage(root.size()*scale,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(scale);image.fill(0);root.render(image)
            if radius:
                point=tree.mapTo(root,QPoint(0,0))*scale
                assert image.pixelColor(point)==root.color_at(24,24),(mode,radius,scale,'hover corner')
for i in range(40):tree.addTopLevelItem(QTreeWidgetItem([f'滚动项 {i+1}','','']))
for mode in ('dark','light'):
    root.config_obj.update(color_mode=mode,corner_radius=24,ui_transparency=0)
    root.setStyleSheet(appearance_style('#cebafa',root.config_obj));tree.setCurrentItem(tree.topLevelItem(tree.topLevelItemCount()-1));tree.scrollToBottom();QTest.qWait(20)
    bar=tree.verticalScrollBar();assert bar.isVisible()
    origin=bar.mapTo(tree,QPoint(0,0));assert origin.x()>0 and origin.y()>=8 and origin.y()+bar.height()<=tree.height()-8
    captured=root.grab().toImage()
    for point in (QPoint(0,0),QPoint(tree.width()-1,tree.height()-1)):
        mapped=tree.mapTo(root,point);assert captured.pixelColor(mapped)==root.color_at(mapped.x(),mapped.y())
root.close()
print('PASS: dark/light solid list backing, 0/10/24px corners, selection/action/scrollbar inset, single 0/30/90% opacity and 1/1.5/2x raster')
