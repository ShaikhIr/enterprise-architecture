"""
Enterprise structured logger using structlog.
Outputs JSON-formatted log entries with correlation ID injection.
"""

import logging
import sys

import structlog

from src.config.settings import settings
from src.observability.correlation import get_correlation_id


def _add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Processor that injects the current correlation ID into every log entry."""
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def _add_module_info(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Processor that adds module and function context."""
    record = event_dict.get("_record")
    if record:
        event_dict["module"] = record.module
        event_dict["function"] = record.funcName
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog with JSON rendering for production
    and colored console output for development.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.DEBUG:
        # Development: colored console output
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Production: JSON output
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance bound to the given name."""
    return structlog.get_logger(name)
