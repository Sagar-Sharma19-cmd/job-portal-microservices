import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(Exception):
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


def error_response(request: Request, error: ApiError):
    request_id = getattr(
        request.state,
        "request_id",
        str(uuid.uuid4()),
    )

    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": request_id,
                "details": error.details,
            }
        },
    )


async def api_error_handler(request: Request, exc: ApiError):
    return error_response(request, exc)


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    error = ApiError(
        status_code=400,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )

    return error_response(request, error)


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    if exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    else:
        code = "NOT_FOUND"

    error = ApiError(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        details={},
    )

    return error_response(request, error)


async def generic_exception_handler(
    request: Request,
    exc: Exception,
):
    error = ApiError(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
        details={},
    )

    return error_response(request, error)