"""
Logging configuration with rotating file handler and ZIP compression.
Provides file-based logging with automatic rotation at 10MB and compressed backups.
"""

import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config.settings import settings


class CompressedRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler that compresses rotated log files with gzip.

    Produces:
        application.log          (current)
        application.log.1.gz     (most recent rotated)
        application.log.2.gz     (older)
        ...
    """

    def rotation_filename(self, default_name: str) -> str:
        """Append .gz extension to rotated filenames."""
        return default_name + ".gz"

    def rotate(self, source: str, dest: str) -> None:
        """Compress the source log file into dest using gzip."""
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)


def configure_file_logging() -> None:
    """
    Set up file-based rotating log handler.

    Configuration:
    - Max file size: 10 MB (configurable via settings)
    - Backup count: 10 (configurable via settings)
    - Format: Structured with timestamp, level, correlation context
    - Compression: gzip for rotated files
    """
    log_path = Path(settings.LOG_FILE_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = CompressedRotatingFileHandler(
        filename=str(log_path),
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        fmt=(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "module": "%(module)s", '
            '"function": "%(funcName)s", "message": "%(message)s"}'
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
