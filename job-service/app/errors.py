import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


class ApiError(Exception):
    """
    Application-level error used by the service routes.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details=None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

        super().__init__(message)


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
):
    request_id = getattr(
        request.state,
        "request_id",
        str(uuid4()),
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or {},
            }
        },
        headers={
            "X-Request-ID": request_id,
        },
    )


def api_error_handler(
    request: Request,
    exc: ApiError,
):
    return _response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        exc.details,
    )


def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    problems = []

    for error in exc.errors():
        location = error.get("loc", ())

        if location:
            field = str(location[-1])
        else:
            field = "body"

        issue = error.get(
            "msg",
            "Invalid value",
        )

        problems.append(
            {
                "field": field,
                "issue": issue,
            }
        )

    return _response(
        request,
        400,
        "VALIDATION_ERROR",
        "Request validation failed",
        {
            "problems": problems,
        },
    )


def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    if exc.status_code == 404:
        return _response(
            request,
            404,
            "NOT_FOUND",
            "Resource not found",
        )

    if exc.status_code == 405:
        return _response(
            request,
            405,
            "METHOD_NOT_ALLOWED",
            "Method not allowed",
        )

    return _response(
        request,
        exc.status_code,
        "HTTP_ERROR",
        str(exc.detail),
    )


def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.error(
        "Unhandled exception",
        exc_info=(
            type(exc),
            exc,
            exc.__traceback__,
        ),
    )

    return _response(
        request,
        500,
        "INTERNAL_ERROR",
        "Internal server error",
    )