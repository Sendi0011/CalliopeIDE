"""
Monitoring and error tracking utilities
Supports structured logging and optional Sentry integration
"""
import os
import logging
import sys
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any
from flask import request, g


# Configure structured logging
def setup_logging(app_name: str = "calliope-ide") -> logging.Logger:
    """
    Configure structured logging with JSON format for production

    Args:
        app_name: Application name for log identification

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(app_name)

    # Set level from environment
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    # JSON-like structured format for easy parsing
    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s", '
        '"module": "%(module)s", "function": "%(funcName)s", '
        '"line": %(lineno)d}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Optional Sentry integration
_sentry_initialized = False

def init_sentry(app) -> bool:
    """
    Initialize Sentry error tracking if enabled

    Environment variables:
        SENTRY_ENABLED: Set to 'true' to enable Sentry
        SENTRY_DSN: Sentry Data Source Name
        SENTRY_ENVIRONMENT: Environment name (production, staging, etc.)
        SENTRY_TRACES_SAMPLE_RATE: Sample rate for performance monitoring (0.0-1.0)

    Returns:
        True if Sentry was initialized, False otherwise
    """
    global _sentry_initialized

    if _sentry_initialized:
        return True

    sentry_enabled = os.getenv('SENTRY_ENABLED', 'false').lower() == 'true'

    if not sentry_enabled:
        app.logger.info("Sentry error tracking is disabled")
        return False

    sentry_dsn = os.getenv('SENTRY_DSN')

    if not sentry_dsn:
        app.logger.warning(
            "SENTRY_ENABLED=true but SENTRY_DSN is not set. "
            "Sentry will not be initialized."
        )
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=os.getenv('SENTRY_ENVIRONMENT', 'production'),
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            integrations=[
                FlaskIntegration(),
                SqlalchemyIntegration(),
            ],
            # Don't send PII
            send_default_pii=False,
            # Capture SQL queries
            _experiments={
                "profiles_sample_rate": 0.1,
            }
        )

        _sentry_initialized = True
        app.logger.info(f"Sentry initialized with environment: {os.getenv('SENTRY_ENVIRONMENT', 'production')}")
        return True

    except ImportError:
        app.logger.warning(
            "Sentry SDK not installed. Install with: pip install sentry-sdk[flask]"
        )
        return False
    except Exception as e:
        app.logger.error(f"Failed to initialize Sentry: {str(e)}")
        return False


def log_request_context(logger: logging.Logger):
    """
    Log request context for debugging

    Args:
        logger: Logger instance to use
    """
    if request:
        logger.info(
            f"Request: {request.method} {request.path} | "
            f"IP: {request.remote_addr} | "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )


def track_error(error: Exception, context: Optional[Dict[str, Any]] = None):
    """
    Track an error with optional context

    Args:
        error: The exception to track
        context: Additional context to attach to the error
    """
    if _sentry_initialized:
        try:
            import sentry_sdk

            if context:
                with sentry_sdk.push_scope() as scope:
                    for key, value in context.items():
                        scope.set_extra(key, value)
                    sentry_sdk.capture_exception(error)
            else:
                sentry_sdk.capture_exception(error)

        except Exception as e:
            # Don't let error tracking crash the app
            logging.error(f"Failed to track error in Sentry: {str(e)}")


def monitor_endpoint(f):
    """
    Decorator to monitor endpoint performance and errors

    Usage:
        @app.route('/api/data')
        @monitor_endpoint
        def get_data():
            return {"data": "value"}
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = datetime.utcnow()
        endpoint = f.__name__

        try:
            result = f(*args, **kwargs)

            # Log successful request
            duration = (datetime.utcnow() - start_time).total_seconds()
            logging.info(
                f"Endpoint: {endpoint} | Duration: {duration:.3f}s | Status: Success"
            )

            return result

        except Exception as e:
            # Log error with context
            duration = (datetime.utcnow() - start_time).total_seconds()

            error_context = {
                'endpoint': endpoint,
                'duration': duration,
                'method': request.method if request else 'Unknown',
                'path': request.path if request else 'Unknown',
            }

            logging.error(
                f"Endpoint: {endpoint} | Duration: {duration:.3f}s | "
                f"Error: {str(e)}",
                exc_info=True
            )

            track_error(e, error_context)
            raise

    return decorated_function


def get_monitoring_stats() -> Dict[str, Any]:
    """
    Get current monitoring configuration status

    Returns:
        Dictionary with monitoring status information
    """
    return {
        'logging_enabled': True,
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
        'sentry_enabled': _sentry_initialized,
        'sentry_environment': os.getenv('SENTRY_ENVIRONMENT', 'production') if _sentry_initialized else None,
    }
