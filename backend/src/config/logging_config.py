"""
File logging configuration with rotating handler and gzip compression.
Writes to log file ONLY — does not add another console handler.

The destination comes from `settings.log_file`, which roots a relative
LOG_FILE_PATH under UPLOAD_DIR so log files and (future) uploads share one
configured storage location.
"""

import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler

from src.config.settings import settings


class CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that compresses rotated log files with gzip."""

    def rotation_filename(self, default_name: str) -> str:
        return default_name + ".gz"

    def rotate(self, source: str, dest: str) -> None:
        with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(source)


def configure_file_logging() -> None:
    """
    Add a rotating file handler to the root logger.
    This writes to the log FILE only (not console).
    Console output is handled by structured_logger.py.
    """
    log_path = settings.log_file

    # Fail loudly and specifically. A bad UPLOAD_DIR (wrong drive, unavailable
    # network share, no write permission) otherwise surfaces as a bare OSError
    # from deep inside the logging module during startup.
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot create the log directory '{log_path.parent}'. "
            f"Check UPLOAD_DIR (currently '{settings.UPLOAD_DIR}') and "
            f"LOG_FILE_PATH (currently '{settings.LOG_FILE_PATH}'): the "
            "resolved path must be writable by the application user."
        ) from exc

    handler = CompressedRotatingFileHandler(
        filename=str(log_path),
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    # File gets a readable format (not JSON)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Only add to root logger — it will receive events from all loggers
    logging.getLogger().addHandler(handler)
