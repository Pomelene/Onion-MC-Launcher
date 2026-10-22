"""Low-alpha accuracy, slider input, resize settling and picker regression fixtures."""
import os
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
native='--native' in sys.argv
os.environ['QT_QPA_PLATFORM']='windows' if native else 'offscreen'
from PySide6.QtCore import Qt,QEvent,QObject,QPoint,QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QStyle,QStyleOptionSlider
from PySide6.QtTest import QTest
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from launcher.qtui.theme import surface_opacity
from launcher.qtui.workspace import InstancePicker

app=QApplication([]);configure_fonts(app);errors=[]
def exception(kind,value,tb):errors.append(str(value));sys.__excepthook__(kind,value,tb)
sys.excepthook=exception
def wait(predicate):
    end=time.monotonic()+8
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate() and not errors,errors
def capture(widget):
    image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);widget.render(image);return image
class PaintCounter(QObject):
    paints=0
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Paint:self.paints+=1
        return False

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='ui-polish-') as directory:
    base=Path(directory);path=base/'onionmcl.json';config=Config(path);config.set('game_dir',str(base/'empty-game'))
    window=MainWindow(path,base)
    if native:window.winId()
    else:window.show()
    wait(lambda:not window.tasks.jobs)
    assert window.title.text()=='' and window.home_button.isHidden()
    window.navigate('settings');assert not window.home_button.isHidden()
    editor=window.settings_editor;window.open_settings_tab(editor.tab_names['外观']);app.processEvents()
    assert set(editor.sliders)=={'ui_transparency','text_transparency','background_transparency','max_download_threads'}
    for key in ('ui_transparency','text_transparency','background_transparency'):
        slider=editor.sliders[key]
        field=editor.fields[key];field.setValue(5);assert slider.value()==5
        slider.setValue(10);assert field.value()==10
    slider=editor.sliders['ui_transparency'];field=editor.fields['ui_transparency']
    if not native:
        slider.setValue(0);app.processEvents();option=QStyleOptionSlider();slider.initStyleOption(option)
        handle=slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,slider)
        QTest.mousePress(slider,Qt.MouseButton.LeftButton,pos=handle.center())
        QTest.mouseMove(slider,QPoint(slider.width()//2,slider.height()//2),10)
        QTest.mouseRelease(slider,Qt.MouseButton.LeftButton,pos=QPoint(slider.width()//2,slider.height()//2))
        assert 0<field.value()<slider.maximum()
        field.lineEdit().setFocus();field.lineEdit().selectAll();QTest.keyClicks(field.lineEdit(),'5');QTest.keyClick(field.lineEdit(),Qt.Key.Key_Return)
        assert field.value()==slider.value()==5
    else:field.setValue(5)
    QTest.qWait(60);assert abs(surface_opacity(window.config_obj)-.95)<1e-6
    for key in ('text_transparency','background_transparency'):editor.fields[key].setValue(0)
    assert editor.flush();assert Config(path).get('ui_transparency')==5
    window.open_settings_tab(editor.tab_names['下载与网络']);app.processEvents()
    threads=editor.fields['max_download_threads'];editor.sliders['max_download_threads'].setValue(17)
    assert threads.value()==17 and threads.suffix()=='' and editor.unit_labels['max_download_threads'].text()=='个'
    threads.setValue(8);assert editor.sliders['max_download_threads'].value()==8
    speed=editor.fields['download_speed_limit'];assert speed.suffix()=='' and speed.text()=='0'
    assert editor.unit_labels['download_speed_limit'].text()=='KiB/s' and editor.number_hints['download_speed_limit'].text()=='不限速'
    speed.setValue(512);assert speed.text()=='512' and editor.number_hints['download_speed_limit'].text()=='';assert editor.flush()
    assert Config(path).get('download_speed_limit')==512 and Config(path).get('max_download_threads')==8
    speed.setValue(0);assert editor.flush()
    if not native:
        wait(lambda:not window.nav_motion.running)
        output=ROOT/'docs/screens/qt-download-controls.png';output.parent.mkdir(parents=True,exist_ok=True);assert capture(window).save(str(output))
    window.navigate('home');root=window.centralWidget();counter=PaintCounter(window);root.installEventFilter(counter)
    rows=[]
    for scope in ('content','window'):
        window.config_obj.set('background_scope',scope)
        for value in (0,1,2,5,10,50,90):
            window.config_obj.set('ui_transparency',value);window.apply_appearance();app.processEvents()
            image=capture(window);alpha=image.pixelColor(600,400).alpha();expected=round(255*(1-value/100))
            assert abs(alpha-expected)<=2,(scope,value,alpha,expected)
            assert window.brand_widget.findChildren(QLabel)[0].palette().color(window.title.foregroundRole()).alpha()==255
            rows.append((scope,value,alpha))
        for value in (0,5,50):
            window.config_obj.set('ui_transparency',value);window.apply_appearance()
            for sizes in (((1600,1000),(1450,920),(1280,840),(1100,740)),((1100,740),(1280,840),(1450,920),(1600,1000))):
                capacity=None
                for width,height in sizes:
                    window.resize(width,height);QTest.qWait(20)
                    assert window.size()==QSize(width,height)
                    image=capture(window);assert abs(image.pixelColor(600,400).alpha()-round(255*(1-value/100)))<=2
                    if width==1600:capacity=root._background_image.size()
                    elif capacity is not None:assert root._background_image.size()==capacity
                QTest.qWait(100);before=counter.paints;QTest.qWait(250)
                assert counter.paints-before<=2,('Repainting continues after resize',counter.paints-before)
                assert not window._resize_flush.isActive()
    window.config_obj.update({'ui_transparency':0,'background_scope':'content'});window.apply_appearance()
    assert window.title.text()=='' and window.home_button.isHidden()
    child=QDialog(window);child.setWindowTitle('子页面');window.show_subpage(child)
    assert not window.home_button.isHidden();child.reject();assert window.home_button.isHidden() and window.title.text()==''
    window.versions=['1.21.1-Fabric','1.20.1-Forge','1.21.4','1.8.9'];window.kinds={v:('Fabric' if 'Fabric' in v else 'Forge' if 'Forge' in v else '原版') for v in window.versions}
    for vid,name in zip(window.versions,('Zeta 生存服','Alpha 工业时代','alpha 创造世界','旧版怀旧')):window.instances.update(vid,name=name,group='测试')
    window.selected_version=window.versions[0]
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance();picker=InstancePicker(window)
        if native:picker.ensurePolished();picker.layout().activate()
        else:picker.show_above(window.quick_button);app.processEvents()
        names=[picker.tree.topLevelItem(i).text(0) for i in range(picker.tree.topLevelItemCount())]
        assert names==sorted(names,key=str.casefold)
        assert picker.tree.currentItem().data(0,Qt.ItemDataRole.UserRole)==window.selected_version
        assert picker.tree.columnCount()==1
        output=ROOT/'docs/screens'/f'qt-instance-picker-{mode}.png';output.parent.mkdir(parents=True,exist_ok=True);assert capture(picker).save(str(output))
        picker.query.setText('no-such-instance');assert picker.tree.topLevelItemCount()==0 and not picker.empty.isHidden()
        picker.query.setText('1.20.1');assert picker.tree.topLevelItemCount()==1
        picker.choose(picker.tree.topLevelItem(0));assert window.selected_version=='1.20.1-Forge' and window.process is None
        picker.deleteLater();app.processEvents()
    if native:assert not any(w.isVisible() for w in app.topLevelWidgets())
    window.close();app.processEvents()
assert not errors,errors
print('PASS: '+('hidden native Windows; ' if native else '')+'linear low transparency '+str(rows)+'; slider/number sync; shrink/grow settled; buffer reuse; home header; sorted searchable picker; no game launched')
