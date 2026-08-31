from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_ctx


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(
        self,
        *,
        code: str = "NOT_FOUND",
        message: str = "Resource was not found.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=404, details=details)


class ForbiddenError(AppError):
    def __init__(
        self,
        *,
        code: str = "FORBIDDEN",
        message: str = "Access denied.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, details=details)


class ConflictError(AppError):
    def __init__(
        self,
        *,
        code: str = "CONFLICT",
        message: str = "Request could not be completed due to a conflict.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=409, details=details)


def _current_request_id() -> str:
    return request_id_ctx.get() or "req_unknown"


def build_error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            request_id=_current_request_id(),
        )
    )
    headers = {"X-Request-ID": _current_request_id()}
    return JSONResponse(status_code=status_code, content=envelope.model_dump(), headers=headers)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "HTTP_ERROR"
    message = str(exc.detail) if exc.detail else "Request failed."
    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code", code))
        message = str(exc.detail.get("message", message))
    return build_error_response(code=code, message=message, status_code=exc.status_code)


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return build_error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        status_code=422,
        details={"errors": exc.errors()},
    )


async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return build_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
