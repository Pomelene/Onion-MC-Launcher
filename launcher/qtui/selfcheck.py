"""Offline, invisible packaged-runtime check. Never uses the user's game library."""
import json,tempfile,time
from unittest.mock import patch
from pathlib import Path
from PySide6.QtWidgets import QApplication,QPushButton
from .accounts import AccountsDialog
from .app import MainWindow
from .widgets import configure_fonts
from ..config import Config


def run(output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    application=QApplication.instance() or QApplication([]);application.setStyle('Fusion');configure_fonts(application)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='qt-runtime-') as folder:
        base=Path(folder);config=Config(base/'config/settings.json');config.set('game_dir',str(base/'empty-library'))
        window=MainWindow(config.path,base);errors=[];window.error=lambda exc:errors.append(str(exc))
        deadline=time.monotonic()+10
        application.processEvents()
        while window.tasks.jobs and time.monotonic()<deadline:application.processEvents();time.sleep(.01)
        assert not window.tasks.jobs,'startup task timeout'
        for page in ('home','versions','download','mods','worlds','logs','settings'):
            window.navigate(page);application.processEvents()
        accounts=AccountsDialog(window)
        entry=next(b for b in accounts.findChildren(QPushButton) if b.text()=='微软正版登录')
        with patch('launcher.qtui.accounts.resolve_client_id',return_value=''):
            entry.click();application.processEvents()
        assert accounts.login.isVisible(),'Microsoft login button did not open the dialog'
        assert callable(accounts.login.open),'QDialog.open is shadowed'
        accounts.login.reject();accounts.reject()
        assert not errors,errors
        assert window.repo.game_dir==base/'empty-library'
        window.close();application.processEvents()
        output.write_text(json.dumps({'result':'pass','packaged_runtime':True,'offscreen':True,'game_started':False,'network_auth':False,'pages':7,'microsoft_login_button':True},indent=2),encoding='utf-8')
    return 0
