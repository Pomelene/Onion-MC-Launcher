"""Portable storage boundaries, using disposable files and synthetic tokens."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from launcher.accounts import AccountRecord, AccountStore
from launcher.config import Config
from launcher.instance import InstanceStore
from launcher.repository import GameRepository
from launcher.secrets import SecretStorageError
from launcher.storage import StorageError, read_section, write_section
from launcher.version_settings import VersionSettingsStore


def test_all_stores_share_one_hidden_file():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'onionmcl.json'
        config = Config(path)
        config.set('max_memory', 6144)
        accounts = AccountStore(path)
        accounts.add(AccountRecord('offline', 'Fixture', 'b'*32))
        instances = InstanceStore(path)
        instances.update('1.21.1', name='Fixture world', group='Test')
        settings = VersionSettingsStore(path)
        settings.set('1.21.1', {'min_memory': 1024, 'isolate': False})
        assert Config(path).get('max_memory') == 6144
        assert AccountStore(path).current().username == 'Fixture'
        assert InstanceStore(path).display_name('1.21.1') == 'Fixture world'
        assert VersionSettingsStore(path).get('1.21.1')['isolate'] is False
        assert list(Path(folder).iterdir()) == [path]
        if os.name == 'nt':
            function = ctypes.WinDLL('kernel32').GetFileAttributesW
            function.argtypes = [ctypes.c_wchar_p]
            function.restype = ctypes.c_uint32
            assert function(str(path)) & 2, 'Hidden flag lost after repeated atomic saves'


def test_legacy_migration_keeps_original_bytes():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        legacy = root / 'config'
        legacy.mkdir()
        payloads = {
            'settings': {'max_memory': 8192, 'accent_color': '#cebafa'},
            'accounts': {'current': 'a'*32, 'accounts': [{'type': 'offline', 'username': 'Fixture', 'uuid': 'a'*32}]},
            'instances': {'1.21.1': {'name': 'Existing world', 'play_seconds': 123}},
            'version_settings': {'1.21.1': {'max_memory': 2048}},
        }
        originals = {}
        for section, data in payloads.items():
            old = legacy / (section + '.json')
            old.write_text(json.dumps(data), encoding='utf-8')
            originals[old] = old.read_bytes()
        path = root / 'onionmcl.json'
        assert Config(path).get('max_memory') == 8192
        assert AccountStore(path).current().username == 'Fixture'
        assert InstanceStore(path).display_name('1.21.1') == 'Existing world'
        assert VersionSettingsStore(path).get('1.21.1')['max_memory'] == 2048
        assert all(old.read_bytes() == data for old, data in originals.items())
        accounts = AccountStore(path)
        accounts.remove('a'*32)
        assert AccountStore(path).current() is None, 'Old accounts were resurrected'


def test_migrated_tokens_and_api_key_are_never_plaintext():
    if os.name != 'nt':
        return
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        legacy = root / 'config'
        legacy.mkdir()
        (legacy/'settings.json').write_text(json.dumps({'curseforge_api_key': 'fixture-cf-secret'}))
        record = {'type': 'microsoft', 'username': 'Fixture', 'uuid': 'a'*32,
                  'access_token': 'fixture-access-secret', 'refresh_token': 'fixture-refresh-secret'}
        (legacy/'accounts.json').write_text(json.dumps({'accounts': [record]}))
        path = root/'onionmcl.json'
        assert Config(path).get('curseforge_api_key') == 'fixture-cf-secret'
        assert AccountStore(path).current().refresh_token == 'fixture-refresh-secret'
        data = path.read_text()
        assert all(secret not in data for secret in ('fixture-cf-secret', 'fixture-access-secret', 'fixture-refresh-secret'))
        assert 'windows-dpapi-v1' in data


def test_failed_encryption_aborts_migration():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        legacy = root/'config'
        legacy.mkdir()
        old = legacy/'settings.json'
        old.write_text(json.dumps({'curseforge_api_key': 'fixture-secret'}))
        before = old.read_bytes()
        with patch('launcher.storage.protect', side_effect=SecretStorageError('unavailable')):
            try:
                Config(root/'onionmcl.json')
            except SecretStorageError:
                pass
            else:
                raise AssertionError('Migration fell back to plaintext')
        assert old.read_bytes() == before
        assert not (root/'onionmcl.json').exists()


def test_unreadable_credentials_remain_intact_on_save():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'onionmcl.json'
        envelope = {'scheme': 'windows-dpapi-v1', 'data': 'fixture-unreadable'}
        write_section(path, 'accounts', {'accounts': [{'type': 'microsoft', 'username': 'Fixture',
                                                       'uuid': 'a'*32, 'protected_secrets': envelope}]})
        with patch('launcher.accounts.unprotect', side_effect=SecretStorageError('different user')):
            accounts = AccountStore(path)
        accounts.save()
        assert not accounts.current().access_token
        assert read_section(path, 'accounts')['accounts'][0]['protected_secrets'] == envelope


def test_corruption_and_newer_formats_are_not_overwritten():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'onionmcl.json'
        for contents in ('{broken', '{"format_version": 999}', '{"format_version":1,"accounts":[]}'):
            path.write_text(contents)
            before = path.read_bytes()
            try:
                Config(path)
            except StorageError:
                pass
            else:
                raise AssertionError('Damaged or unsupported document was silently reset')
            assert path.read_bytes() == before


def test_invalid_legacy_file_prevents_partial_migration():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root/'config').mkdir()
        (root/'config/settings.json').write_text('{"max_memory":8192}')
        (root/'config/accounts.json').write_text('{broken')
        try:
            Config(root/'onionmcl.json')
        except StorageError:
            pass
        else:
            raise AssertionError('Partial migration committed')
        assert not (root/'onionmcl.json').exists()


def test_failed_replace_preserves_document_and_account_state():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'onionmcl.json'
        accounts = AccountStore(path)
        accounts.add(AccountRecord('offline', 'Fixture', 'a'*32))
        before = path.read_bytes()
        with patch('launcher.storage._replace', side_effect=OSError('fixture write failure')):
            try:
                accounts.add(AccountRecord('offline', 'Other', 'b'*32))
            except OSError:
                pass
            else:
                raise AssertionError('Failed replacement reported success')
        assert path.read_bytes() == before
        assert len(accounts.accounts) == 1
        assert list(Path(folder).iterdir()) == [path]


def test_threaded_section_updates_preserve_other_sections():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'onionmcl.json'
        def save(section):
            for counter in range(12):
                write_section(path, section, {'counter': counter})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, ['settings', 'accounts', 'instances', 'version_settings']))
        for section in ('settings', 'accounts', 'instances', 'version_settings'):
            assert read_section(path, section) == {'counter': 11}


def test_windows_process_writers_preserve_sections():
    if os.name != 'nt':
        return
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'onionmcl.json'
        code = 'import sys; from launcher.storage import write_section; [write_section(sys.argv[1],sys.argv[2],{"counter":i}) for i in range(8)]'
        sections = ('settings', 'accounts', 'instances', 'version_settings')
        children = [subprocess.Popen([sys.executable, '-c', code, str(path), section],
                                    cwd=Path(__file__).resolve().parents[1],
                                    creationflags=subprocess.CREATE_NO_WINDOW) for section in sections]
        try:
            for child in children:
                assert child.wait(timeout=30) == 0
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        for section in sections:
            assert read_section(path, section) == {'counter': 7}


def test_run_directory_reads_unified_instance_override():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root/'onionmcl.json'
        config = Config(path)
        config.set('game_dir', str(root/'library'))
        config.set('version_isolation', True)
        overrides = VersionSettingsStore(path)
        overrides.set('1.21.1', {'isolate': False})
        repository = GameRepository(config)
        assert repository.run_dir('1.21.1') == root/'library'
        overrides.set('1.21.1', {'isolate': True})
        assert repository.run_dir('1.21.1') == root/'library/versions/1.21.1'
