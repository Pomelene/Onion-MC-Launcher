"""Offscreen updater consent, quiet failure, settings and handoff regression."""
import os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.deps/qt')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.updates import UpdatePrompt,VersionPicker
from launcher.qtui.widgets import configure_fonts
from launcher.download import DownloadCancelled
from tests.test_launcher_updates import release,entry
from launcher import updates

app=QApplication([]);app.setStyle('Fusion');configure_fonts(app)
def wait(window):
    app.processEvents();deadline=time.monotonic()+10
    while (window.tasks.jobs or window.updater.check_tasks.jobs) and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    assert not window.tasks.jobs and not window.updater.check_tasks.jobs

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='qt-update-') as folder:
    root=Path(folder);config=Config(root/'onionmcl.json');config.set('game_dir',str(root/'game'))
    window=MainWindow(config.path,root);window.show();wait(window);controller=window.updater
    window.error=lambda error:errors.append(str(error));errors=[]
    with patch('launcher.qtui.updates.updates.can_install',return_value=True),patch('launcher.qtui.updates.updates.finish_previous_updates',return_value=False),patch('launcher.qtui.updates.updates.check_update') as check:
        config=window.config_obj;config.set('check_launcher_updates',False);controller.startup();assert not check.called
        config.set('check_launcher_updates',True)
    with patch('launcher.qtui.updates.updates.check_update',side_effect=OSError('fixture offline')),patch.object(UpdatePrompt,'exec') as prompt,patch.object(QMessageBox,'information') as info,patch.object(QMessageBox,'warning') as warning:
        controller.check();wait(window)
        assert not prompt.called and not info.called and not warning.called and not errors
        assert not controller.checking
    with patch('launcher.qtui.updates.updates.check_update',return_value=None),patch.object(UpdatePrompt,'exec') as prompt,patch.object(QMessageBox,'information') as info:
        controller.check();wait(window);assert not prompt.called and not info.called
        controller.check(manual=True);wait(window);assert info.call_count==1
    with patch('launcher.qtui.updates.updates.check_update',return_value=release()),patch.object(UpdatePrompt,'exec',return_value=QDialog.DialogCode.Rejected) as prompt:
        window.mutating=True;controller.check();wait(window)
        assert not prompt.called and controller.timer.isActive()
        window.mutating=False;controller.offer();assert prompt.call_count==1 and controller.pending is None
        assert window.isVisible()
        window.mutating=True;controller.check();wait(window)
        config.set('check_launcher_updates',False);controller.offer()
        assert controller.pending is None and prompt.call_count==1
        window.mutating=False;config.set('check_launcher_updates',True)
    from PySide6.QtGui import QImage
    prompt=UpdatePrompt(window,release());prompt.show();app.processEvents()
    image=QImage(prompt.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);prompt.render(image)
    assert image.save(str(ROOT/'docs/screens/qt-launcher-update.png'));prompt.close()
    history=updates.parse_manifest({'schema_version':1,'releases':[entry(updates.LAUNCHER_VERSION,33),entry('0.2.0',1)]})
    picker=VersionPicker(window,history)
    assert not picker.proceed.isEnabled()
    picker.versions.setCurrentIndex(1)
    assert picker.proceed.isEnabled() and picker.selected_release().version=='0.2.0' and not picker.warning.isHidden()
    picker.show();app.processEvents();image=QImage(picker.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0);picker.render(image)
    assert image.save(str(ROOT/'docs/screens/qt-version-history.png'));picker.close()
    with patch('launcher.qtui.updates.updates.fetch_releases',return_value=[history[1]]),patch.object(VersionPicker,'exec',return_value=QDialog.DialogCode.Accepted),patch.object(controller,'install') as install:
        controller.manage_versions();wait(window)
        assert install.call_count==1 and install.call_args.args[0].version=='0.2.0'
    # Source-based UI regression never launches or replaces a real executable.
    staged=root/'fixture.exe';staged.write_bytes(b'fixture only')
    with patch('launcher.qtui.updates.updates.can_install',return_value=True),patch('launcher.qtui.updates.updates.download_update',return_value=staged),patch('launcher.qtui.updates.updates.launch_replacement') as launch,patch.object(QApplication,'quit') as quit_app:
        controller.install(release());wait(window);app.processEvents()
        assert launch.call_count==1 and launch.call_args.args[1]==staged and quit_app.call_count==1
        assert Config(config.path).get('launcher_window_width')>0
    def cancel(release,exe,downloader,job):
        job.cancel.set();raise DownloadCancelled('fixture cancel')
    with patch('launcher.qtui.updates.updates.can_install',return_value=True),patch('launcher.qtui.updates.updates.download_update',side_effect=cancel),patch('launcher.qtui.updates.updates.launch_replacement') as launch:
        controller.installing=False;controller.install(release());wait(window);app.processEvents()
        assert not launch.called and not controller.installing and not errors
    with patch('launcher.qtui.updates.updates.can_install',return_value=True),patch('launcher.qtui.updates.updates.download_update',side_effect=ValueError('fixture hash mismatch')),patch('launcher.qtui.updates.updates.launch_replacement') as launch:
        controller.install(release());wait(window);app.processEvents()
        assert not launch.called and not controller.installing and errors==['fixture hash mismatch'];errors.clear()
    window.navigate('settings');window.settings_editor.select_tab(window.settings_editor.tab_names['启动器行为'])
    assert 'check_launcher_updates' in window.settings_editor.fields
    window.settings_editor.fields['check_launcher_updates'].setChecked(False)
    assert window.settings_editor.flush() and not Config(config.path).get('check_launcher_updates')
    controller.timer.stop();controller.apply_timer.stop();window.close()
print('PASS: quiet checks, opt-out, manual check, busy deferral, consent, saved settings, cancellation and verified handoff')
