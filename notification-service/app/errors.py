import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", ""),
                "details": details or {},
            }
        },
    )


async def api_error_handler(request: Request, exc: ApiError):
    return error_response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        exc.details,
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    problems = []

    for error in exc.errors():
        location = error.get("loc", ())
        field_parts = [
            str(part) for part in location if part not in ("body", "query", "path")
        ]

        problems.append(
            {
                "field": ".".join(field_parts) or "request",
                "issue": error.get("msg", "Invalid value"),
            }
        )

    return error_response(
        request,
        400,
        "VALIDATION_ERROR",
        "Request validation failed",
        {"problems": problems},
    )


async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    if exc.status_code == 404:
        code, message = "NOT_FOUND", "Resource not found"
    elif exc.status_code == 405:
        code, message = "METHOD_NOT_ALLOWED", "Method not allowed"
    else:
        code, message = "HTTP_ERROR", str(exc.detail)

    return error_response(request, exc.status_code, code, message)


async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error while processing request", exc_info=exc)

    return error_response(
        request,
        500,
        "INTERNAL_ERROR",
        "An unexpected internal error occurred",
    )