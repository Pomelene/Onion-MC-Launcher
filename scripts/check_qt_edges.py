"""Rounded settings groups must not leak hover fill or duplicate terminal borders."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit
from PySide6.QtTest import QTest
from launcher.qtui.widgets import SettingsSection,SettingsRow,setting_row,column,configure_fonts
from launcher.qtui.theme import appearance_style
app=QApplication([]);configure_fonts(app)
root=QWidget();root.config_obj={};root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
layout=column(root,12,0);section=SettingsSection();layout.addWidget(section)
for title in ('First','Middle','Last'):setting_row(section.body,title,'',QLineEdit('Value'))
root.resize(480,240);root.show();app.processEvents()
surface=section.body.parentWidget();rows=surface.findChildren(SettingsRow)
assert len(rows)==3
for mode in ('dark','light'):
    for radius in (0,10,24):
        root.config_obj.update(color_mode=mode,corner_radius=radius)
        root.setStyleSheet(appearance_style('#cebafa',root.config_obj));app.processEvents()
        # The circular slider handle must stay seven pixels, even at radius 0/24.
        assert 'width:14px; margin:-5px 0; border-radius:7px' in root.styleSheet()
        for hovered in (rows[0],rows[-1]):
            QTest.mouseMove(hovered,QPoint(2,2));QTest.qWait(10)
            for scale in (1,1.5,2):
                image=QImage(surface.size()*scale,QImage.Format.Format_ARGB32_Premultiplied)
                image.setDevicePixelRatio(scale);image.fill(0);surface.render(image,renderFlags=QWidget.RenderFlag.DrawChildren)
                if radius:
                    assert image.pixelColor(0,0).alpha()==0,(mode,radius,scale,'top')
                    assert image.pixelColor(image.width()-1,image.height()-1).alpha()==0,(mode,radius,scale,'bottom')
                assert image.pixelColor(image.width()//2,image.height()//2).alpha()>0
        root.grab().save(str(ROOT/'tmp'/f'edges-{mode}-{radius}.png'))
root.close()
print('PASS: first/last hover clipping, 0/10/24px corners, 1/1.5/2x rendering, light/dark and circular slider geometry')
