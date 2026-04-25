"""
Monitoring utilities - structured JSON logging and observability
"""
import logging
import json
import time
import uuid
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from flask import Flask, request, g


# ── JSON log formatter ────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON for easy parsing and ingestion."""

    LEVEL_MAP = {
        'DEBUG': 'debug',
        'INFO': 'info',
        'WARNING': 'warning',
        'ERROR': 'error',
        'CRITICAL': 'critical',
    }

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': self.LEVEL_MAP.get(record.levelname, record.levelname.lower()),
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Attach request_id when available (set by before_request hook)
        try:
            request_id = getattr(g, 'request_id', None)
            if request_id:
                log_entry['request_id'] = request_id
        except RuntimeError:
            pass  # Outside request context

        # Include extra fields forwarded via logger.info(..., extra={...})
        _std_keys = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
            'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'processName', 'process', 'message',
            'taskName',
        }
        for key in set(record.__dict__) - _std_keys:
            log_entry[key] = getattr(record, key)

        # Attach exception info when present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_entry, default=str)


# ── Logger factory ────────────────────────────────────────────────────────────

def setup_logging(name: str, level: str = 'INFO') -> logging.Logger:
    """
    Create and return a logger that emits structured JSON to stdout.

    Args:
        name:  Logger name (e.g. 'calliope-ide').
        level: Minimum log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    logger.propagate = False
    return logger


# ── Flask request lifecycle hooks ─────────────────────────────────────────────

def _before_request() -> None:
    """Attach a unique request ID and record the start time."""
    g.request_id = str(uuid.uuid4())
    g.request_start_time = time.perf_counter()


def _after_request(response):
    """Log a structured summary of the completed request."""
    logger = logging.getLogger('calliope-ide')

    duration_ms = round(
        (time.perf_counter() - getattr(g, 'request_start_time', time.perf_counter())) * 1000,
        2,
    )

    logger.info(
        'api_request',
        extra={
            'event': 'api_request',
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': duration_ms,
            'request_id': getattr(g, 'request_id', None),
            'remote_addr': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
        },
    )

    response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
    return response


def init_request_logging(app: Flask) -> None:
    """
    Register before/after request hooks on app for automatic request logging.

    Call this once during application setup, after app is created.
    """
    app.before_request(_before_request)
    app.after_request(_after_request)


# ── Sentry stub (kept for API compatibility) ──────────────────────────────────

def init_sentry(app: Flask) -> None:
    """No-op — Sentry integration is intentionally disabled."""
    pass


# ── Endpoint monitoring decorator ─────────────────────────────────────────────

def monitor_endpoint(func):
    """
    Decorator that logs execution time and errors for a specific endpoint.

    Usage:
        @app.route('/some/path')
        @monitor_endpoint
        def my_view():
            ...
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger('calliope-ide')
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                'endpoint_ok',
                extra={
                    'event': 'endpoint_ok',
                    'endpoint': func.__name__,
                    'duration_ms': duration_ms,
                },
            )
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                'endpoint_error',
                exc_info=True,
                extra={
                    'event': 'endpoint_error',
                    'endpoint': func.__name__,
                    'duration_ms': duration_ms,
                    'error': str(exc),
                },
            )
            raise

    return wrapper


# ── Monitoring stats ──────────────────────────────────────────────────────────

def get_monitoring_stats() -> Dict[str, Any]:
    """Return basic observability configuration info."""
    return {
        'enabled': True,
        'logging': {
            'format': 'json',
            'level': logging.getLevelName(
                logging.getLogger('calliope-ide').level
            ),
        },
        'sentry': {'enabled': False},
        'request_tracing': {'enabled': True, 'header': 'X-Request-ID'},
    }


# ── Error tracking helpers ────────────────────────────────────────────────────

def track_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log an exception with optional context metadata.

    Args:
        error:   The exception to record.
        context: Arbitrary key/value pairs to include in the log entry.
    """
    logger = logging.getLogger('calliope-ide')
    extra: Dict[str, Any] = {'event': 'tracked_error', 'error_type': type(error).__name__}
    if context:
        extra['context'] = context
    logger.error(str(error), exc_info=True, extra=extra)


def capture_exception(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Alias for track_error (backward compatibility)."""
    track_error(error, context)