"""One error envelope for the whole API:

    {"error": {"code": "FORBIDDEN", "message": "...", "details": [...], "request_id": "..."}}
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("api")


class ApiError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 details: list[dict[str, Any]] | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        self.headers = headers


class Unauthorized(ApiError):
    status_code, code = 401, "UNAUTHORIZED"

    def __init__(self, message: str = "Authentication required", *, code: str | None = None):
        super().__init__(message, code=code, headers={"WWW-Authenticate": "Bearer"})


class Forbidden(ApiError):
    status_code, code = 403, "FORBIDDEN"


class NotFound(ApiError):
    status_code, code = 404, "NOT_FOUND"


class Conflict(ApiError):
    status_code, code = 409, "CONFLICT"


class Unprocessable(ApiError):
    status_code, code = 422, "VALIDATION_ERROR"


class ServiceUnavailable(ApiError):
    status_code, code = 503, "UPSTREAM_UNAVAILABLE"


def _body(code: str, message: str, request: Request, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message,
                           "request_id": getattr(request.state, "request_id", None)}
    if details:
        err["details"] = details
    return {"error": err}


def _format_validation(errors: list[Any]) -> list[dict[str, Any]]:
    out = []
    for e in errors:
        loc = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")]
        out.append({"field": ".".join(loc) or "body", "message": str(e.get("msg", "invalid")).removeprefix("Value error, ")})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message, request, exc.details),
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(_body("VALIDATION_ERROR", "Request validation failed", request,
                                  _format_validation(list(exc.errors()))), status_code=422)

    @app.exception_handler(ValidationError)
    async def _pyd(request: Request, exc: ValidationError):
        return JSONResponse(_body("VALIDATION_ERROR", "Request validation failed", request,
                                  _format_validation(exc.errors())), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, str(exc.detail), request), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Never leak internals: log the stack trace, return an opaque message.
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", None))
        return JSONResponse(_body("INTERNAL_ERROR", "Something went wrong", request), status_code=500)
