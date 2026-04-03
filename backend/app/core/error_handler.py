"""Application errors and global exception handling."""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.log_safety import mask_sensitive_text

class AppError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "APP_ERROR",
        details: dict[str, Any] | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


class AssistantError(AppError):
    """Assistant request failed."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="ASSISTANT_ERROR",
            details=details,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class GeminiAPIError(AppError):
    """Gemini upstream request failed."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="GEMINI_API_ERROR",
            details=details,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


def build_error_payload(exc: AppError | HTTPException, *, default_code: str = "HTTP_ERROR") -> dict[str, Any]:
    """Convert an exception to a consistent response payload."""
    if isinstance(exc, AppError):
        return {
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        }

    return {
        "error": {
            "code": default_code,
            "message": str(exc.detail),
            "details": {},
        }
    }


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions with structured logging."""
    logger.bind(component="error").exception(
        "Unhandled exception on {method} {path} request_id={request_id}\n{traceback}",
        method=request.method,
        path=request.url.path,
        request_id=getattr(request.state, "request_id", "unknown"),
        traceback=traceback.format_exc(),
    )

    if isinstance(exc, AppError):
        return JSONResponse(status_code=exc.status_code, content=build_error_payload(exc))

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(exc, default_code="HTTP_ERROR"),
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": mask_sensitive_text("系统出现了未预期错误，请稍后重试。"),
                "details": {},
            }
        },
    )
