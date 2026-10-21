# -*- coding: utf-8 -*-
"""启动器自身日志：滚动文件 + 控制台。"""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOGGER: logging.Logger | None = None


def setup_logging(log_dir: Path, level: str = "info", to_console: bool = True) -> logging.Logger:
    """初始化滚动日志，返回全局 logger（重复调用不重复挂 handler）。"""
    global _LOGGER
    logger = logging.getLogger("craftbridge")
    if logger.handlers:
        return logger
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = TimedRotatingFileHandler(log_dir / "launcher.log", when="midnight",
                                  backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    _LOGGER = logger
    return logger


def get_logger() -> logging.Logger:
    return _LOGGER or logging.getLogger("craftbridge")
