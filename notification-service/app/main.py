from contextlib import asynccontextmanager
import logging
import pathlib
import sys
import uuid
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import INTERNAL_TOKEN, PORT, SERVICE_NAME
from app.database import get_conn, init_db
from app.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

deregister_service = None
registry_registered = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global deregister_service, registry_registered

    init_db()

    # Add the repository root so this service can use the shared registry.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

    try:
        from common.registration import register_service, deregister_service as deregister

        deregister_service = deregister
        register_service(SERVICE_NAME, "127.0.0.1", PORT)
        registry_registered = True
    except ImportError:
        print("common.registration not available yet - running without the registry")

    try:
        yield
    finally:
        if registry_registered and deregister_service is not None:
            deregister_service()


app = FastAPI(
    title="Notification Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(ApiError, api_error_handler)

app.add_exception_handler(
    RequestValidationError,
    validation_error_handler,
)

app.add_exception_handler(
    StarletteHTTPException,
    http_error_handler,
)

app.add_exception_handler(Exception, unexpected_error_handler)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    public_paths = {"/health", "/docs", "/redoc", "/openapi.json"}

    # Protect internal endpoints while allowing health checks and API documentation.
    if request.url.path not in public_paths:
        supplied_token = request.headers.get("X-Internal-Token")

        if not INTERNAL_TOKEN or supplied_token != INTERNAL_TOKEN:
            response = JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "A valid internal token is required",
                        "request_id": request_id,
                        "details": {},
                    }
                },
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Served-By"] = f"{SERVICE_NAME}-{PORT}"
            return response

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Served-By"] = f"{SERVICE_NAME}-{PORT}"
    return response


@app.get("/health")
def health():
    try:
        with get_conn() as connection:
            connection.execute("SELECT 1").fetchone()

        return {
            "service": SERVICE_NAME,
            "instance_id": f"{SERVICE_NAME}-{PORT}",
            "status": "UP",
            "db": "UP",
        }
    except Exception:
        logger.exception("Notification Service health check failed")
        return {
            "service": SERVICE_NAME,
            "instance_id": f"{SERVICE_NAME}-{PORT}",
            "status": "DOWN",
            "db": "DOWN",
        }


app.include_router(router)