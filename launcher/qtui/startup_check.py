"""Run the real application entry point offscreen with disposable user data."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def run(output):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from . import app as entry
    from .. import log
    from ..config import Config
    from ..paths import LAUNCHER_VERSION

    output = Path(output).resolve()
    original_window, original_logging = entry.MainWindow, log.setup_logging
    original_hook = sys.excepthook
    failures = []
    result = {'result': 'fail', 'launcher_version': LAUNCHER_VERSION,
              'real_entry_point': True, 'visible_windows': False}
    with tempfile.TemporaryDirectory(prefix='onion-startup-') as folder:
        root = Path(folder)
        config = Config(root/'onionmcl.json')
        config.set('game_dir', str(root/'game'))
        os.environ['WEBVIEW2_USER_DATA_FOLDER'] = str(root/'webview')
        log.setup_logging = lambda **kwargs: original_logging(root/'logs', **kwargs)
        sys.excepthook = lambda kind, error, tb: failures.append(str(error))

        def create_window():
            window = original_window(config.path, root)
            deadline = time.monotonic() + 30
            timer = QTimer(window)

            def inspect():
                if window.tasks.jobs and time.monotonic() < deadline:
                    return
                timer.stop()
                try:
                    assert QApplication.platformName() == 'offscreen'
                    assert not window.tasks.jobs, 'Startup jobs timed out'
                    assert window.isVisible(), 'Main window never opened'
                    assert not failures, failures
                    window.navigate('tools')
                    expected = {'skins', 'seedmap', 'tasks', 'services'} if LAUNCHER_VERSION.endswith('-T') else {'skins', 'seedmap', 'tasks'}
                    assert set(window.nav) == expected, 'Edition navigation mismatch'
                    window.navigate('home')
                    assert window.close(), 'Main window failed to close'
                    saved = Config(config.path)
                    assert saved.get('launcher_window_width') > 0
                    assert saved.get('launcher_window_height') > 0
                    result.update(result='pass', edition_navigation=True,
                                  size_persisted=True, isolated_data=True)
                except Exception as error:
                    failures.append(str(error))
                QApplication.instance().exit(0 if result['result'] == 'pass' else 1)

            timer.timeout.connect(inspect)
            timer.start(50)
            return window

        entry.MainWindow = create_window
        try:
            code = entry.main()
            assert code == 0, 'Application event loop failed'
        except Exception as error:
            failures.append(str(error))
        finally:
            entry.MainWindow, log.setup_logging = original_window, original_logging
            sys.excepthook = original_hook
            # Release Windows file handles before deleting the temporary directory.
            logger = log.get_logger()
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
        if failures:
            result.update(result='fail', errors=failures)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['result'] == 'pass' else 1
