# error_handlers.py - Custom error handling and exceptions
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from structured_logging import get_logger

logger = get_logger("error_handlers")

class CRMException(Exception):
    """Base CRM exception.

    Permite tanto CRMException("mensagem") quanto CRMException(code="...", message="...").
    """

    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        # Se apenas uma string for passada, tratamos como message e usamos um code genérico.
        if message is None:
            message = code
            code = "ERROR"

        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(CRMException):
    """Validation error"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details
        )

class AuthenticationError(CRMException):
    """Authentication error"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            code="AUTHENTICATION_ERROR",
            message=message,
            status_code=401
        )

class AuthorizationError(CRMException):
    """Authorization error"""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            code="AUTHORIZATION_ERROR",
            message=message,
            status_code=403
        )

class NotFoundError(CRMException):
    """Resource not found"""
    def __init__(self, resource: str, resource_id: Any = None):
        msg = f"{resource} not found"
        if resource_id:
            msg += f" (ID: {resource_id})"
        super().__init__(
            code="NOT_FOUND",
            message=msg,
            status_code=404
        )

class ConflictError(CRMException):
    """Resource conflict"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
            details=details
        )

class RateLimitError(CRMException):
    """Rate limit exceeded"""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=message,
            status_code=429
        )

class InternalServerError(CRMException):
    """Internal server error"""
    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            code="INTERNAL_SERVER_ERROR",
            message=message,
            status_code=500
        )

def register_error_handlers(app: FastAPI):
    """Register error handlers with FastAPI app"""
    
    @app.exception_handler(CRMException)
    async def crm_exception_handler(request: Request, exc: CRMException):
        logger.error(
            "CRM Exception occurred",
            code=exc.code,
            error_message=exc.message,
            path=request.url.path,
            method=request.method,
            details=exc.details
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            exception_type=type(exc).__name__,
            error_message=str(exc),
            path=request.url.path,
            method=request.method
        )
        
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        )
