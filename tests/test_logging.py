"""Launcher log locations and migration use disposable directories only."""
import ctypes
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from launcher import log
from launcher.paths import default_log_dir


@contextmanager
def isolated_logger():
    logger = logging.getLogger('craftbridge')
    previous = logger.handlers[:], logger.level, log._LOGGER
    logger.handlers = []
    try:
        yield logger
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        logger.handlers, logger.level, log._LOGGER = previous


def test_logs_default_to_hidden_onion_and_keep_rotation():
    with tempfile.TemporaryDirectory() as folder, isolated_logger():
        root = Path(folder)
        with patch('launcher.paths.app_root', return_value=root):
            assert default_log_dir() == root / '.onion' / 'logs'
            logger = log.setup_logging(to_console=False)
            logger.info('fixture log entry')
            for handler in logger.handlers:
                handler.flush()
            path = default_log_dir() / 'launcher.log'
            assert 'fixture log entry' in path.read_text(encoding='utf-8')
            assert not (root / 'logs').exists()
            assert logger.handlers[0].backupCount == 7
            assert log.setup_logging(to_console=False) is logger and len(logger.handlers) == 1
            if os.name == 'nt':
                get_attributes = ctypes.WinDLL('kernel32').GetFileAttributesW
                get_attributes.argtypes = [ctypes.c_wchar_p]
                get_attributes.restype = ctypes.c_uint32
                assert get_attributes(str(root / '.onion')) & 2


def test_logs_migrate_known_files_and_remove_only_empty_old_directory():
    with tempfile.TemporaryDirectory() as folder, isolated_logger():
        root = Path(folder)
        old = root / 'logs'; old.mkdir()
        payloads = {'launcher.log': b'old current\n', 'launcher.log.2026-10-22': b'old rotated\n'}
        for name, content in payloads.items():
            (old / name).write_bytes(content)
        with patch('launcher.paths.app_root', return_value=root):
            log.setup_logging(to_console=False)
        target = root / '.onion' / 'logs'
        archive, = target.glob('legacy-*')
        assert {item.name: item.read_bytes() for item in archive.iterdir()} == payloads
        assert not old.exists() and (target / 'launcher.log').exists()


def test_logs_preserve_unknown_files_and_existing_destination_logs():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder); old = root / 'logs'; old.mkdir()
        (old / 'notes.txt').write_bytes(b'user data')
        (old / 'launcher.log.notes').write_bytes(b'not our rotation')
        (old / 'launcher.log').write_bytes(b'old log')
        target = root / '.onion' / 'logs'; target.mkdir(parents=True)
        (target / 'launcher.log').write_bytes(b'new log')
        for content in (b'old log', b'another old log'):
            (old / 'launcher.log').write_bytes(content)
            assert not log._migrate_legacy_logs(target)
        archives = list(target.glob('legacy-*'))
        assert len(archives) == 2
        assert {next(archive.iterdir()).read_bytes() for archive in archives} == {b'old log', b'another old log'}
        assert (target / 'launcher.log').read_bytes() == b'new log'
        assert (old / 'notes.txt').read_bytes() == b'user data'
        assert (old / 'launcher.log.notes').read_bytes() == b'not our rotation'


def test_logs_leave_locked_legacy_file_and_continue_logging():
    with tempfile.TemporaryDirectory() as folder, isolated_logger():
        root = Path(folder); old = root / 'logs'; old.mkdir()
        source = old / 'launcher.log'; source.write_bytes(b'locked log')
        with patch('launcher.paths.app_root', return_value=root), patch.object(Path, 'rename', side_effect=PermissionError('fixture lock')):
            logger = log.setup_logging(to_console=False)
        assert source.read_bytes() == b'locked log'
        for handler in logger.handlers:
            handler.flush()
        assert '保留原文件' in (root / '.onion/logs/launcher.log').read_text(encoding='utf-8')
        assert not list((root / '.onion/logs').glob('legacy-*'))


def test_logs_skip_legacy_directory_links():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder); old = root / 'logs'; old.mkdir()
        (old / 'launcher.log').write_bytes(b'untouched')
        target = root / '.onion' / 'logs'; target.mkdir(parents=True)
        with patch.object(Path, 'is_symlink', return_value=True):
            assert not log._migrate_legacy_logs(target)
        assert (old / 'launcher.log').read_bytes() == b'untouched'
        assert not list(target.iterdir())


def test_logs_explicit_directory_stays_explicit():
    with tempfile.TemporaryDirectory() as folder, isolated_logger():
        root = Path(folder)
        with patch('launcher.paths.app_root', return_value=root):
            log.setup_logging(root / 'diagnostics', to_console=False)
        assert (root / 'diagnostics/launcher.log').exists()
        assert not (root / '.onion').exists()


def test_logs_hidden_attribute_failure_does_not_lose_logging():
    with tempfile.TemporaryDirectory() as folder, isolated_logger():
        root = Path(folder)
        with patch('launcher.paths.app_root', return_value=root), patch('launcher.log._hide_directory', side_effect=OSError('fixture failure')):
            logger = log.setup_logging(to_console=False)
        for handler in logger.handlers:
            handler.flush()
        assert '隐藏属性' in (root / '.onion/logs/launcher.log').read_text(encoding='utf-8')
