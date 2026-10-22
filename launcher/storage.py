"""One portable, hidden JSON document shared by the launcher's stores.

Section updates reread under a path lock, so separate stores cannot overwrite
each other. Windows instances also share a named mutex. Old files are read
only during first migration and are never deleted or rewritten.
"""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from .secrets import protect

FILENAME = 'onionmcl.json'
VERSION = 1
SECTIONS = ('settings', 'accounts', 'instances', 'version_settings')
_locks = {}
_registry_lock = threading.Lock()


class StorageError(RuntimeError):
    pass


def is_portable(path):
    return Path(path).name.lower() == FILENAME


@contextmanager
def _locked(path):
    key = os.path.normcase(str(Path(path).resolve()))
    with _registry_lock:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        handle = None
        if os.name == 'nt':
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            name = 'Local\\OnionMCL.Storage.' + hashlib.sha256(key.encode()).hexdigest()
            handle = kernel.CreateMutexW(None, False, name)
            if not handle:
                raise StorageError('无法锁定启动器数据，原文件未修改。')
            result = kernel.WaitForSingleObject(handle, 10000)
            if result not in (0, 0x80):
                kernel.CloseHandle(handle)
                raise StorageError('启动器数据正在被其他进程使用，请稍后重试。')
        try:
            yield
        finally:
            if handle:
                kernel.ReleaseMutex(handle)
                kernel.CloseHandle(handle)


def _hide(path):
    if os.name != 'nt':
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    kernel.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.SetFileAttributesW.restype = wintypes.BOOL
    attributes = kernel.GetFileAttributesW(str(path))
    if attributes != 0xffffffff and attributes & 2:
        return
    if attributes == 0xffffffff or not kernel.SetFileAttributesW(str(path), attributes | 2):
        raise StorageError('无法设置 onionmcl.json 的隐藏属性。')


def _replace(temporary, target):
    if os.name == 'nt' and target.exists():
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        kernel.ReplaceFileW.restype = wintypes.BOOL
        for attempt in range(7):
            if kernel.ReplaceFileW(str(target), str(temporary), None, 2, None, None):
                return
            error = ctypes.get_last_error()
            # Virus scanners/indexers can briefly hold the previous document.
            # Retry replacement; never delete the destination as a fallback.
            if error not in (5, 32, 33, 1175) or attempt == 6:
                raise OSError(error, '无法原子保存启动器数据')
            time.sleep(min(.02 * 2**attempt, .4))
    else:
        os.replace(temporary, target)


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.onionmcl-', delete=False) as output:
            temporary = Path(output.name)
            if os.name != 'nt':
                os.chmod(temporary, 0o600)
            json.dump(document, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        _hide(temporary)
        _replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _legacy_payload(section, payload):
    """Encrypt old plaintext credentials before writing the new document."""
    if section == 'settings':
        secret = payload.pop('curseforge_api_key', '')
        if secret:
            payload['protected_settings'] = protect({'curseforge_api_key': secret})
    elif section == 'accounts':
        records = payload.get('accounts', [])
        if not isinstance(records, list):
            raise StorageError('旧账户配置格式无效，已停止迁移，原文件未修改。')
        for item in records:
            if not isinstance(item, dict):
                continue
            values = {key: item.pop(key, '') for key in ('access_token', 'refresh_token', 'client_token')}
            if any(value not in ('', '0', None) for value in values.values()):
                item['protected_secrets'] = protect(values)
    return payload


def _read(path):
    if path.exists():
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise StorageError('onionmcl.json 无法读取，已停止加载以保留原文件。') from error
        if not isinstance(document, dict) or document.get('format_version') != VERSION:
            raise StorageError('onionmcl.json 格式或版本不受支持，原文件未修改。')
        if any(not isinstance(document.get(key, {}), dict) for key in SECTIONS):
            raise StorageError('onionmcl.json 数据分区无效，原文件未修改。')
        _hide(path)
        return document
    document = {'format_version': VERSION, **{key: {} for key in SECTIONS}}
    imported = []
    for section in SECTIONS:
        old = path.parent / 'config' / (section + '.json')
        if not old.exists():
            continue
        try:
            payload = json.loads(old.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise StorageError(f'旧配置 {old.name} 无法读取，已停止迁移，原文件未修改。') from error
        if not isinstance(payload, dict):
            raise StorageError(f'旧配置 {old.name} 格式无效，已停止迁移。')
        document[section] = _legacy_payload(section, payload)
        imported.append(old.name)
    document['migration'] = {'legacy_files': imported}
    _write(path, document)
    return document


def read_section(path, section):
    path = Path(path)
    if not is_portable(path):
        return json.loads(path.read_text(encoding='utf-8'))
    with _locked(path):
        return _read(path).get(section, {})


def write_section(path, section, payload):
    if section not in SECTIONS or not isinstance(payload, dict):
        raise ValueError('无效的数据分区')
    path = Path(path)
    with _locked(path):
        document = _read(path)
        document[section] = payload
        _write(path, document)
