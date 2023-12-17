import logging
from datetime import datetime
from typing import Optional

from config import app_conf

log_level: int = logging.getLevelName(app_conf.server.log_level.upper())


class SmolLogger:
    source: str

    def __init__(self, source: Optional[str]):
        self.source = source

    def log(self, msg: str, level: int = logging.INFO):
        return log_any(msg, level, self.source)

    def info(self, msg: str):
        return log_any(msg, logging.INFO, self.source)

    def warn(self, msg: str):
        return log_any(msg, logging.WARN, self.source)

    def debug(self, msg: str):
        return log_any(msg, logging.DEBUG, self.source)


def log_any(msg: str, level: int = logging.INFO, source: str = None):
    if log_level <= level:
        before: str = f"{datetime.utcnow().isoformat()} {logging.getLevelName(level)}"
        if source is not None:
            before = f"{before} {source}"
        print(f"{before}: {msg}")


def log_info(msg: str, source: str = None):
    return log_any(msg, logging.INFO, source)


def log_warn(msg: str, source: str = None):
    return log_any(msg, logging.WARN, source)


def log_debug(msg: str, source: str = None):
    return log_any(msg, logging.DEBUG, source)