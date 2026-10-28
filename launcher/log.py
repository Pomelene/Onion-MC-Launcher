# -*- coding: utf-8 -*-
"""启动器自身日志：滚动文件 + 控制台。"""

import logging
import os
import re
import tempfile
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOGGER: logging.Logger | None = None


class SafeFormatter(logging.Formatter):
    def format(self,record):
        from .crash import redact
        return redact(super().format(record))


def _hide_directory(path: Path) -> None:
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    kernel.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.SetFileAttributesW.restype = wintypes.BOOL
    attributes = kernel.GetFileAttributesW(str(path))
    if attributes == 0xffffffff or not kernel.SetFileAttributesW(str(path), attributes | 2):
        raise ctypes.WinError(ctypes.get_last_error())


def _migrate_legacy_logs(log_dir: Path) -> list[str]:
    """Archive only our old filenames, without overwriting files or following links."""
    legacy = log_dir.parent.parent / 'logs'
    warnings = []
    if legacy.is_symlink() or legacy.is_junction() or not legacy.is_dir():
        return warnings
    archive = None
    try:
        for source in legacy.iterdir():
            if not re.fullmatch(r'launcher\.log(?:\.\d{4}-\d{2}-\d{2})?', source.name):
                continue
            if source.is_symlink() or not source.is_file():
                continue
            try:
                if archive is None:
                    archive = Path(tempfile.mkdtemp(prefix='legacy-', dir=log_dir))
                # A fresh, exclusive archive directory avoids name conflicts with
                # both current logs and previous migrations. A locked file stays put.
                source.rename(archive / source.name)
            except OSError:
                warnings.append('旧启动器日志暂时无法迁移，已保留原文件。')
        if archive is not None:
            try:
                archive.rmdir()  # Only removes an empty archive after failed moves.
            except OSError:
                pass
        try:
            legacy.rmdir()  # Unknown files or subdirectories prevent removal.
        except OSError:
            pass
    except OSError:
        warnings.append('旧日志目录暂时无法读取，已保留原目录。')
    return warnings


def setup_logging(log_dir: Path | None = None, level: str = "info", to_console: bool = True) -> logging.Logger:
    """初始化滚动日志，返回全局 logger（重复调用不重复挂 handler）。"""
    global _LOGGER
    logger = logging.getLogger("craftbridge")
    if logger.handlers:
        return logger
    warnings = []
    if log_dir is None:
        from .paths import default_log_dir
        log_dir = default_log_dir()
        from .safety import contained
        contained(log_dir/'launcher.log',log_dir.parent.parent)
        log_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            _hide_directory(log_dir.parent)
        except OSError:
            warnings.append('无法设置 .onion 的隐藏属性，日志仍保存在该目录。')
        log_dir.mkdir(parents=True, exist_ok=True)
        warnings.extend(_migrate_legacy_logs(log_dir))
    else:
        log_dir = Path(log_dir)
        for path in (log_dir.parent,log_dir,log_dir/'launcher.log'):
            if path.is_symlink() or path.is_junction():raise OSError('日志路径不能是目录链接或符号链接')
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate=False
    fmt = SafeFormatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = TimedRotatingFileHandler(log_dir / "launcher.log", when="midnight",
                                  backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    _LOGGER = logger
    for message in warnings:
        logger.warning(message)
    return logger


def get_logger() -> logging.Logger:
    return _LOGGER or logging.getLogger("craftbridge")
