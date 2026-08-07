# structured_logging.py - Structured logging with JSON
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pythonjsonlogger import jsonlogger
import sys

# Correlation IDs must be per-request. Storing them on the logger instance made
# concurrent requests overwrite each other's ID, so log lines were attributed to
# the wrong request under any real load.
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class StructuredLogger:
    """Structured logging with correlation IDs"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_handler()

    def _setup_handler(self):
        """Setup JSON logging handler"""
        # Guard against duplicate handlers: get_logger() may rebuild this
        # object for the same underlying logger, which previously attached a
        # new handler each time and emitted every line N times.
        if any(getattr(h, "_crm_structured", False) for h in self.logger.handlers):
            return
        handler = logging.StreamHandler(sys.stdout)
        handler._crm_structured = True
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s %(correlation_id)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def set_correlation_id(self, correlation_id: Optional[str] = None):
        """Set correlation ID for tracing"""
        _correlation_id.set(correlation_id or str(uuid.uuid4()))

    def get_correlation_id(self) -> str:
        """Get current correlation ID"""
        current = _correlation_id.get()
        if not current:
            current = str(uuid.uuid4())
            _correlation_id.set(current)
        return current
    
    # Keys the stdlib logging module owns on every LogRecord. Passing any of
    # them through `extra` raises "KeyError: Attempt to overwrite ... in
    # LogRecord", so callers using e.g. message=... would crash the logger
    # instead of logging. We namespace them rather than drop them.
    _RESERVED_LOG_KEYS = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    })

    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Add standard context to log"""
        safe_extra = {
            (f"ctx_{key}" if key in self._RESERVED_LOG_KEYS else key): value
            for key, value in extra.items()
        }
        context = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": self.get_correlation_id(),
            **safe_extra
        }
        return context
    
    def debug(self, message: str, **extra):
        """Log debug message"""
        self.logger.debug(message, extra=self._add_context(extra))
    
    def info(self, message: str, **extra):
        """Log info message"""
        self.logger.info(message, extra=self._add_context(extra))
    
    def warning(self, message: str, **extra):
        """Log warning message"""
        self.logger.warning(message, extra=self._add_context(extra))
    
    def error(self, message: str, **extra):
        """Log error message"""
        self.logger.error(message, extra=self._add_context(extra))
    
    def critical(self, message: str, **extra):
        """Log critical message"""
        self.logger.critical(message, extra=self._add_context(extra))

# Global logger instance
_logger = StructuredLogger("crm_app")

def get_logger(name: str = "crm_app") -> StructuredLogger:
    """Get logger instance"""
    global _logger
    if _logger.logger.name != name:
        _logger = StructuredLogger(name)
    return _logger

def set_correlation_id(correlation_id: Optional[str] = None):
    """Set correlation ID globally"""
    _logger.set_correlation_id(correlation_id)

def get_correlation_id() -> str:
    """Get current correlation ID"""
    return _logger.get_correlation_id()
