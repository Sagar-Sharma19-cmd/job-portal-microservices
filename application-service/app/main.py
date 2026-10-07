import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import INTERNAL_TOKEN, PORT, SERVICE_NAME
from app.database import get_conn, init_db
from app.errors import (
    ApiError,
    api_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_error_handler,
)
from app.routes import router

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException


ROOT_DIR = Path(__file__).resolve().parents[2]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    try:
        from common.registration import (
            register_service,
            deregister_service,
        )

        register_service(
            SERVICE_NAME,
            "127.0.0.1",
            PORT,
        )

        print(
            f"[REGISTRY] {SERVICE_NAME} registered on port {PORT}"
        )

    except ImportError:
        deregister_service = None

        print(
            "[REGISTRY] common.registration not available; "
            "running without registration."
        )

    yield

    if deregister_service:
        try:
            deregister_service(
                SERVICE_NAME,
                "127.0.0.1",
                PORT,
            )
        except Exception:
            pass


app = FastAPI(
    title="Application Service",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_middleware(
    request: Request,
    call_next,
):
    request_id = request.headers.get(
        "X-Request-ID",
        str(uuid.uuid4()),
    )

    request.state.request_id = request_id

    public_paths = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    if request.url.path not in public_paths:
        token = request.headers.get("X-Internal-Token")

        if token != INTERNAL_TOKEN:
            response = JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid or missing internal token",
                        "request_id": request_id,
                        "details": {},
                    }
                },
            )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Served-By"] = (
                f"{SERVICE_NAME}-{PORT}"
            )

            return response

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Served-By"] = (
        f"{SERVICE_NAME}-{PORT}"
    )

    return response


@app.get("/health")
def health():
    db_status = "UP"

    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        db_status = "DOWN"

    overall_status = "UP" if db_status == "UP" else "DOWN"

    return {
        "service": SERVICE_NAME,
        "instance_id": f"{SERVICE_NAME}-{PORT}",
        "status": overall_status,
        "db": db_status,
    }


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
    HTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    generic_exception_handler,
)