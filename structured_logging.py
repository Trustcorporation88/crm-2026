# structured_logging.py - Structured logging with JSON
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pythonjsonlogger import jsonlogger
import sys

class StructuredLogger:
    """Structured logging with correlation IDs"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.correlation_id = None
        self._setup_handler()
    
    def _setup_handler(self):
        """Setup JSON logging handler"""
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s %(correlation_id)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
    
    def set_correlation_id(self, correlation_id: Optional[str] = None):
        """Set correlation ID for tracing"""
        self.correlation_id = correlation_id or str(uuid.uuid4())
    
    def get_correlation_id(self) -> str:
        """Get current correlation ID"""
        if not self.correlation_id:
            self.set_correlation_id()
        return self.correlation_id
    
    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Add standard context to log"""
        context = {
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": self.get_correlation_id(),
            **extra
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
