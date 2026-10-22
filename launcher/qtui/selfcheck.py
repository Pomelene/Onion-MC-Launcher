"""Offline, invisible packaged-runtime check. Never uses the user's game library."""
import json,tempfile,time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt,QBuffer,QByteArray,QIODevice
from PySide6.QtGui import QImage,QIcon,QSurface
from .accounts import AccountsDialog
from .app import MainWindow
from .widgets import configure_fonts
from ..config import Config
from ..paths import LAUNCHER_VERSION


def check_images(window):
    """Exercise Qt's bundled image codecs without importing Pillow."""
    source=QImage(16,16,QImage.Format.Format_RGB32);source.fill(0xff40b060)
    for fmt in ('PNG','JPEG','WEBP','TIFF'):
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert source.save(buffer,fmt),'Image encoder missing: '+fmt
        buffer.close();decoded=QImage.fromData(data)
        assert decoded.size()==source.size() and decoded.pixelColor(8,8).green()>140,fmt
    svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="#40b060"/></svg>'
    assert QImage.fromData(svg).pixelColor(8,8).green()>140
    import base64
    gif=QImage.fromData(base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'))
    assert not gif.isNull() and gif.width()==1
    icon=QIcon(str(Path(__file__).resolve().parents[2]/'assets/craftbridge.ico'))
    assert not icon.pixmap(32,32).isNull()
    return ['PNG','JPEG','WEBP','TIFF','SVG','GIF','ICO']


def render_hidden(window):
    window.ensurePolished()
    image=QImage(window.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    window.render(image)
    assert image.pixelColor(image.width()//2,image.height()//2).alpha()>0
    return image


def check_transparency(window):
    previous={key:window.config_obj.get(key) for key in ('ui_transparency','text_transparency','background_scope')}
    try:
        window.navigate('home')
        for value in (0,5,90):
            window.config_obj.update({'ui_transparency':value,'text_transparency':0,'background_scope':'window'})
            window.apply_appearance();QApplication.processEvents()
            image=render_hidden(window)
            assert abs(image.pixelColor(600,400).alpha()-round(255*(1-value/100)))<=2,'Window backdrop alpha must follow the configured percentage'
        assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert window.windowOpacity()==1,'Global window opacity would also fade text'
        assert window.title.palette().color(window.title.foregroundRole()).alpha()==255
    finally:
        window.config_obj.update(previous);window.apply_appearance()


def run_raster(output):
    """Use the real Windows QPA plugin but keep every window hidden."""
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    application=QApplication.instance() or QApplication([]);application.setStyle('Fusion');configure_fonts(application)
    assert application.platformName()=='windows'
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='qt-raster-') as folder:
        base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'empty-library'))
        window=MainWindow(config.path,base);window.winId()
        application.processEvents()
        deadline=time.monotonic()+10
        while window.tasks.jobs and time.monotonic()<deadline:application.processEvents();time.sleep(.01)
        assert not window.tasks.jobs
        assert window.windowHandle().surfaceType()==QSurface.SurfaceType.RasterSurface
        for mode in ('dark','light'):
            window.config_obj.update({'color_mode':mode});window.apply_appearance()
            for page in ('home','versions','settings'):
                window.navigate(page);render_hidden(window)
        check_transparency(window);formats=check_images(window)
        assert not any(w.isVisible() for w in application.topLevelWidgets()),'Raster probe must not show windows'
        window.close();application.processEvents()
        output.write_text(json.dumps({'result':'pass','platform':'windows','surface':'RasterSurface',
            'visible_windows':False,'fixture_only':True,'image_formats':formats,'color_modes':['dark','light'],'per_pixel_transparency':True,'independent_text_alpha':True},indent=2),encoding='utf-8')
    return 0


def run(output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    application=QApplication.instance() or QApplication([]);application.setStyle('Fusion');configure_fonts(application)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='qt-runtime-') as folder:
        base=Path(folder);config=Config(base/'onionmcl.json');config.set('game_dir',str(base/'empty-library'))
        window=MainWindow(config.path,base);errors=[];window.error=lambda exc:errors.append(str(exc))
        deadline=time.monotonic()+10
        application.processEvents()
        while window.tasks.jobs and time.monotonic()<deadline:application.processEvents();time.sleep(.01)
        assert not window.tasks.jobs,'startup task timeout'
        for page in ('home','versions','download','instance','settings','about'):
            window.navigate(page);application.processEvents()
        assert window.settings_editor.fields['auto_memory'] is not None
        assert {'ui_transparency','text_transparency','background_transparency','max_download_threads'}<=window.settings_editor.sliders.keys()
        assert window.settings_editor.fields['download_speed_limit'].specialValueText()==''
        assert window.settings_editor.unit_labels['download_speed_limit'].text()=='KiB/s'
        assert window.settings_editor.number_hints['download_speed_limit'].text()=='不限速'
        assert window.settings_editor.unit_labels['max_memory'].text()=='MiB'
        from .color_picker import ColorPicker
        picker=ColorPicker('#cebafa',window.settings_editor)
        picker.ensurePolished();picker.resize(picker.sizeHint());application.processEvents()
        assert picker.hex.text()=='#cebafa' and tuple(field.value() for field in picker.rgb)==(206,186,250)
        picker.rgb[0].setValue(128);assert picker.color.name()=='#80bafa'
        sample=QImage(picker.size(),QImage.Format.Format_ARGB32_Premultiplied);sample.fill(0);picker.render(sample)
        assert not sample.isNull();picker.reject()
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert not any(b.text()=='保存设置' for b in window.settings_editor.findChildren(QPushButton))
        window.settings_editor.fields['window_width'].setValue(1280)
        window.flush_settings()
        assert Config(config.path).get('window_width')==1280
        assert window.nav['instance'].isEnabled() is False
        from .installer import InstallDialog
        installer=InstallDialog(window)
        # Instantiate without opening: packaged imports and filters need no network.
        installer.active=False
        from ..version import VersionEntry
        installer.entries=[VersionEntry('1.21.1','release',''),VersionEntry('24w14a','snapshot','')]
        installer.render_versions();assert installer.tree.topLevelItemCount()==1
        accounts=AccountsDialog(window)
        entry=next(b for b in accounts.findChildren(QPushButton) if b.text()=='微软正版登录')
        # Keep the frozen diagnostic independent of unittest and its mock tools.
        from . import accounts as accounts_module
        original_resolver=accounts_module.resolve_client_id
        accounts_module.resolve_client_id=lambda *args,**kwargs:''
        try:
            entry.click();application.processEvents()
        finally:accounts_module.resolve_client_id=original_resolver
        assert accounts.login.isVisible(),'Microsoft login button did not open the dialog'
        assert callable(accounts.login.open),'QDialog.open is shadowed'
        accounts.login.reject();accounts.reject()
        assert not errors,errors
        assert window.repo.game_dir==base/'empty-library'
        formats=check_images(window)
        import ssl
        context=ssl.create_default_context()
        assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        assert len(ssl.RAND_bytes(16))==16
        for mode in ('light','dark'):
            editor=window.settings_editor
            editor.fields['color_mode'].setCurrentIndex(editor.fields['color_mode'].findData(mode))
            window.flush_settings();window.navigate('home');render_hidden(window)
        check_transparency(window)
        assert window.accounts.path==window.instances.path==window.version_settings.path==config.path
        assert config.path.exists()
        if __import__('os').name=='nt':
            import ctypes
            get_attributes=ctypes.WinDLL('kernel32').GetFileAttributesW
            get_attributes.argtypes=[ctypes.c_wchar_p];get_attributes.restype=ctypes.c_uint32
            assert get_attributes(str(config.path)) & 2
        window.close();application.processEvents()
        output.write_text(json.dumps({'result':'pass','launcher_version':LAUNCHER_VERSION,'packaged_runtime':True,'offscreen':True,'game_started':False,'network_auth':False,'pages':6,'microsoft_login_button':True,'grouped_settings':True,'installer_filters':True,'unified_hidden_storage':True,'frameless_window':True,'automatic_settings_save':True,'image_formats':formats,'python_tls':True,'raster_render':True,'color_modes':['light','dark'],'per_pixel_transparency':True,'independent_text_alpha':True},indent=2),encoding='utf-8')
    return 0
