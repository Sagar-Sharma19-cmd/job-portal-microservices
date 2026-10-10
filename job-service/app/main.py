import pathlib
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import (
    INTERNAL_TOKEN,
    PORT,
    SERVICE_NAME,
)
from .database import (
    get_conn,
    init_db,
)
from .errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database must exist before the service starts accepting requests.
    init_db()

    registration_module = None

    # Add repo root so common/ can be imported.
    sys.path.insert(
        0,
        str(
            pathlib.Path(__file__)
            .resolve()
            .parents[2]
        ),
    )

    try:
        from common.registration import (
            register_service,
            deregister_service,
        )

        registration_module = (
            register_service,
            deregister_service,
        )

        register_service(
            SERVICE_NAME,
            "127.0.0.1",
            PORT,
        )

    except ImportError:
        print(
            "common.registration not available yet - "
            "running without the registry"
        )

    try:
        yield

    finally:
        if registration_module:
            _, deregister_service = registration_module

            deregister_service(
                SERVICE_NAME,
                "127.0.0.1",
                PORT,
            )


app = FastAPI(
    title=SERVICE_NAME,
    lifespan=lifespan,
)

app.include_router(router)

app.add_exception_handler(
    ApiError,
    api_error_handler,
)

app.add_exception_handler(
    RequestValidationError,
    validation_error_handler,
)

app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)


@app.middleware("http")
async def request_middleware(
    request: Request,
    call_next,
):
    # Reuse the caller's ID or generate one for tracing.
    request_id = (
        request.headers.get("X-Request-ID")
        or str(uuid.uuid4())
    )

    request.state.request_id = request_id

    public_paths = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    if request.url.path not in public_paths:
        if (
            request.headers.get("X-Internal-Token")
            != INTERNAL_TOKEN
        ):
            response = api_error_handler(
                request,
                ApiError(
                    401,
                    "UNAUTHORIZED",
                    "Unauthorized",
                ),
            )

            if request.url.path.startswith(
                "/api/v1/jobs"
            ):
                response.headers[
                    "Deprecation"
                ] = "true"

            response.headers[
                "X-Served-By"
            ] = f"{SERVICE_NAME}-{PORT}"

            return response

    response = await call_next(request)

    response.headers[
        "X-Request-ID"
    ] = request_id

    # Every V1 jobs response carries the required deprecation header.
    if request.url.path.startswith(
        "/api/v1/jobs"
    ):
        response.headers[
            "Deprecation"
        ] = "true"

    response.headers[
        "X-Served-By"
    ] = f"{SERVICE_NAME}-{PORT}"

    return response


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute(
                "SELECT 1"
            ).fetchone()

        return {
            "service": SERVICE_NAME,
            "instance_id": (
                f"{SERVICE_NAME}-{PORT}"
            ),
            "status": "UP",
            "db": "UP",
        }

    except Exception:
        return {
            "service": SERVICE_NAME,
            "instance_id": (
                f"{SERVICE_NAME}-{PORT}"
            ),
            "status": "DOWN",
            "db": "DOWN",
        }