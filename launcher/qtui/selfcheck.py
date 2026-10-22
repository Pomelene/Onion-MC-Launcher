"""Offline, invisible packaged-runtime check. Never uses the user's game library."""
import json,tempfile,time
from unittest.mock import patch
from pathlib import Path
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt
from .accounts import AccountsDialog
from .app import MainWindow
from .widgets import configure_fonts
from ..config import Config


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
        with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
            entry.click();application.processEvents()
        assert accounts.login.isVisible(),'Microsoft login button did not open the dialog'
        assert callable(accounts.login.open),'QDialog.open is shadowed'
        accounts.login.reject();accounts.reject()
        assert not errors,errors
        assert window.repo.game_dir==base/'empty-library'
        assert window.accounts.path==window.instances.path==window.version_settings.path==config.path
        assert config.path.exists()
        if __import__('os').name=='nt':
            import ctypes
            get_attributes=ctypes.WinDLL('kernel32').GetFileAttributesW
            get_attributes.argtypes=[ctypes.c_wchar_p];get_attributes.restype=ctypes.c_uint32
            assert get_attributes(str(config.path)) & 2
        window.close();application.processEvents()
        output.write_text(json.dumps({'result':'pass','packaged_runtime':True,'offscreen':True,'game_started':False,'network_auth':False,'pages':6,'microsoft_login_button':True,'grouped_settings':True,'installer_filters':True,'unified_hidden_storage':True,'frameless_window':True,'automatic_settings_save':True},indent=2),encoding='utf-8')
    return 0
