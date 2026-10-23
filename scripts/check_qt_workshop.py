"""Deterministic workshop/instance UI checks; disposable data and no real login."""
import os,sys,json,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt'),str(ROOT/'tests')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QEvent,QPointF
from PySide6.QtGui import QImage,QColor,QPainter,QMouseEvent
from PySide6.QtWidgets import QApplication
from launcher.config import Config
from launcher.accounts import AccountRecord,offline_uuid
from launcher.qtui.app import MainWindow
from launcher.qtui.widgets import configure_fonts
from test_workshop import png

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app);errors=[]
def hook(kind,value,tb):errors.append(str(value));traceback.print_exception(kind,value,tb)
sys.excepthook=hook
def pump(predicate,seconds=30):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert predicate(),'UI task timed out'
def snapshot(window,name):
    app.processEvents();image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);window.render(image)
    path=ROOT/'docs/screens'/name;path.parent.mkdir(exist_ok=True);assert image.save(str(path))

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='workshop-ui-') as tmp:
    base=Path(tmp);game=base/'game';vid='1.20.6';folder=game/'versions'/vid;folder.mkdir(parents=True)
    (folder/(vid+'.json')).write_text(json.dumps({'id':vid,'mainClass':'Main','libraries':[]}))
    config=Config(base/'onionmcl.json');config.set('game_dir',str(game))
    window=MainWindow(config.path,base);window.error=lambda error:errors.append(str(error));window.show()
    pump(lambda:not window.tasks.jobs and bool(window.versions));window.set_selected(vid)
    run=window.repo.run_dir(vid);schematics=run/'schematics';schematics.mkdir(parents=True)
    (schematics/'建筑').mkdir();(schematics/'红石机器.litematic').write_bytes(b'invalid metadata, still listed')
    (schematics/'建筑/城堡.litematic').write_bytes(b'example')
    shots=run/'screenshots';shots.mkdir()
    for i in range(30):
        image=QImage(640,360,QImage.Format.Format_RGB32);image.fill(QColor.fromHsv((i*17)%360,90,150))
        painter=QPainter(image);painter.setPen(QColor('#efe5ff'));painter.drawText(image.rect(),Qt.AlignmentFlag.AlignCenter,f'Screenshot {i+1}');painter.end()
        image.save(str(shots/f'2026-10-22_12.00.{i:02d}.png'))
    window.navigate('schematics');pump(lambda:not window.tasks.jobs)
    browser=window.instance_workspace.pages['schematics'].file_browser
    assert browser.entries[0].directory;browser.enter(schematics/'建筑');pump(lambda:not window.tasks.jobs)
    assert len(browser.entries)==1;browser.parent_folder();pump(lambda:not window.tasks.jobs)
    snapshot(window,'qt-schematics.png')
    window.navigate('screenshots');pump(lambda:not window.tasks.jobs)
    gallery=window.instance_workspace.pages['screenshots'].file_browser
    assert len(gallery.entries)==30 and gallery.entries[0].path.name.endswith('29.png')
    assert gallery.per_page is None and gallery.gallery.model().rowCount()==30
    assert not hasattr(gallery,'previous') and not hasattr(gallery,'next')
    view=gallery.gallery;view.scrollToBottom();app.processEvents();pump(lambda:not window.tasks.jobs)
    assert view.visualRect(view.model().index(29)).intersects(view.viewport().rect())
    pump(lambda:view.gallery_model.key(gallery.entries[-1]) in view.gallery_model.cache)
    assert len(view.gallery_model.cache)<=96
    gallery.query.setText('12.00.29');app.processEvents();assert view.model().rowCount()==1
    gallery.query.clear();app.processEvents();view.scrollToTop();pump(lambda:not window.tasks.jobs)
    pump(lambda:all(view.gallery_model.key(gallery.entries[i]) in view.gallery_model.cache for i in view.visible_rows()))
    assert view.visualRect(view.model().index(0)).top()==view.visualRect(view.model().index(4)).top(),'Gallery should fit at least five columns at 1440px'
    snapshot(window,'qt-screenshots.png')
    from dataclasses import replace
    stress=[replace(gallery.entries[0],modified=gallery.entries[0].modified+i) for i in range(3000)]
    view.replace(stress);app.processEvents();view.scrollToBottom()
    pump(lambda:view.gallery_model.key(stress[-1]) in view.gallery_model.cache)
    assert view.model().rowCount()==3000 and len(view.gallery_model.cache)<=96
    assert view.visualRect(view.model().index(2999)).intersects(view.viewport().rect())
    view.replace(gallery.entries);app.processEvents()
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        for width in (1100,1440,1920):
            window.resize(width,900);app.processEvents()
            pump(lambda:all(view.gallery_model.key(gallery.entries[i]) in view.gallery_model.cache for i in view.visible_rows()))
            snapshot(window,f'qt-screenshots-{mode}-{width}.png')
    window.resize(1440,900);window.config_obj.set('color_mode','dark');window.apply_appearance()
    account=AccountRecord('offline','WorkshopPlayer',offline_uuid('WorkshopPlayer'));window.accounts.add(account);window.accounts.set_current(account.uuid)
    window.navigate('tools');wardrobe=window.workshop.views['skins']
    skin=base/'purple-skin.png';skin.write_bytes(png());path=wardrobe.library.import_skin(skin);wardrobe.choose(path);wardrobe.refresh()
    wardrobe.apply_local();assert wardrobe.library.selected(account.uuid)
    assert not wardrobe.upload.isVisible() and wardrobe.apply.isEnabled()
    snapshot(window,'qt-workshop-skins.png')
    preview=wardrobe.preview;before=preview.image.copy()
    def skin_frame():
        image=QImage(preview.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);preview.render(image);return image
    def mouse(kind,x,y,button,buttons):
        point=QPointF(x,y);event=QMouseEvent(kind,point,point,button,buttons,Qt.KeyboardModifier.NoModifier);app.sendEvent(preview,event)
    initial=skin_frame();textures=dict(preview._textures)
    mouse(QEvent.Type.MouseButtonPress,70,70,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove,130,100,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert preview.yaw!=-.38 and preview.pitch!=.16
    rotated=skin_frame();assert rotated!=initial and before==preview.image
    assert all(preview._textures[key] is value for key,value in textures.items()),'Dragging must reuse decoded/shaded textures'
    mouse(QEvent.Type.MouseButtonRelease,130,100,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    angles=preview.yaw,preview.pitch;mouse(QEvent.Type.MouseMove,150,140,Qt.MouseButton.NoButton,Qt.MouseButton.NoButton)
    assert (preview.yaw,preview.pitch)==angles
    mouse(QEvent.Type.MouseButtonDblClick,70,70,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    assert preview.yaw==-.38 and preview.pitch==.16 and preview.drag is None
    assert skin_frame()==initial
    mouse(QEvent.Type.MouseButtonPress,70,70,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove,70,-10000,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert abs(preview.pitch)<1.571
    mouse(QEvent.Type.MouseButtonDblClick,70,70,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    window.open_tools_tab('seedmap');mapping=window.workshop.views['seedmap'];mapping.seed.setText('-3829811542736183482')
    assert mapping.version.currentText()=='26.3'
    for spin,value in zip(mapping.coords,(68148,80990,77)):spin.setValue(value)
    mapping.render_map();pump(lambda:not mapping.busy and not window.tasks.jobs)
    assert mapping.canvas.tiles and not mapping.canvas.image.isNull()
    canvas=mapping.canvas
    def map_mouse(kind,x,y,button,buttons):
        point=QPointF(x,y);event=QMouseEvent(kind,point,point,button,buttons,Qt.KeyboardModifier.NoModifier);app.sendEvent(canvas,event)
    initial_x=canvas.view.x;tiles=list(canvas.tiles)
    map_mouse(QEvent.Type.MouseButtonPress,180,180,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    map_mouse(QEvent.Type.MouseMove,240,195,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert canvas.view.x==initial_x-60*canvas.view.blocks_per_pixel,'Pan must update before mouse release'
    assert list(canvas.tiles)==tiles,'Dragging must preserve visible raster tiles'
    map_mouse(QEvent.Type.MouseButtonRelease,240,195,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    pump(lambda:not mapping.busy and not window.tasks.jobs)
    anchor=QPointF(130,210);world=canvas.world(anchor);before=canvas.view.blocks_per_pixel
    canvas.zoom_to(before/2,anchor);samples=[]
    def animation_done():
        samples.append(canvas.view.blocks_per_pixel)
        return canvas.animation.state()!=canvas.animation.State.Running
    pump(animation_done)
    assert len(set(samples))>3 and all(a>=b for a,b in zip(samples,samples[1:]))
    assert all(abs(a-b)<1e-7 for a,b in zip(world,canvas.world(anchor))),'Wheel zoom must preserve the cursor anchor'
    pump(lambda:not mapping.busy and not window.tasks.jobs)
    tiles=list(canvas.tiles);mapping.set_layers(False);app.processEvents()
    assert not canvas.enabled_layers and list(canvas.tiles)==tiles and not window.tasks.jobs,'Filters must not regenerate terrain'
    mapping.set_layers(True)
    map_mouse(QEvent.Type.MouseButtonPress,290,240,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    map_mouse(QEvent.Type.MouseButtonRelease,290,240,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    assert canvas.selection and mapping.copy.isEnabled()
    mapping.copy_selection();_,x,z=canvas.selection;assert app.clipboard().text()==f'X {x} Z {z}'
    mapping.copy_selection(True);assert app.clipboard().text()==f'/tp @s {x} ~ {z}'
    pump(lambda:not mapping.busy and not window.tasks.jobs)
    mapping.seed.setText('123');mapping.render_map();mapping.seed.setText('-3829811542736183482');mapping.render_map()
    pump(lambda:not mapping.busy and not window.tasks.jobs)
    assert all(key[0]==mapping.epoch for key in canvas.tiles),'Obsolete seed results must be discarded'
    assert sum(t[0].sizeInBytes()+len(t[1])*2 for t in canvas.tiles.values())<=32*1024*1024
    # Return to a representative overview for layout snapshots.
    canvas.view.blocks_per_pixel=4;mapping.set_layers(False)
    for name in ('村庄','沙漠神殿','海底神殿','远古城市'):mapping.checks[name].setChecked(True)
    mapping.refresh_view();pump(lambda:not mapping.busy and not window.tasks.jobs)
    snapshot(window,'qt-workshop-seedmap.png')
    old=mapping.coords[0].value();mapping.pan(256,0);pump(lambda:not mapping.busy and not window.tasks.jobs);assert mapping.coords[0].value()==old+256
    for mode in ('dark','light'):
        window.config_obj.set('color_mode',mode);window.apply_appearance()
        for width in (1100,1440,1920):
            window.resize(width,900);app.processEvents();pump(lambda:not mapping.busy and not window.tasks.jobs);snapshot(window,f'qt-workshop-map-{mode}-{width}.png')
            assert mapping.go.isVisible() and mapping.canvas.width()>=320
    window.navigate('home');window.close();pump(lambda:not window.tasks.jobs)
    assert not errors,errors
print(json.dumps({'result':'pass','fixtures_only':True,'pages':['schematics','screenshots','skins','seedmap'],'continuous_screenshots':True,'last_screenshot_reachable':True,'local_skin_selection':True,'real_seedmap':True,'no_live_upload':True}))
