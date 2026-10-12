import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import INTERNAL_TOKEN, PORT, SERVICE_NAME
from app.database import get_conn, init_db
from app.errors import ApiError, api_error_handler, generic_exception_handler, http_exception_handler, validation_error_handler
from app.routes import router

@asynccontextmanager
async def lifespan(app):
    init_db()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    try:
        from common.registration import register_service, deregister_service
        register_service(SERVICE_NAME, "127.0.0.1", PORT)
    except ImportError:
        deregister_service = None
        print("common.registration not available yet - running without the registry")
    yield
    if deregister_service:
        deregister_service(SERVICE_NAME, "127.0.0.1", PORT)

app = FastAPI(title="Candidate Service", lifespan=lifespan)
@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    if request.url.path not in {"/health", "/docs", "/redoc", "/openapi.json"} and request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        response = JSONResponse(status_code=401, content={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing internal token", "request_id": request_id, "details": {}}})
    else: response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Served-By"] = f"{SERVICE_NAME}-{PORT}"
    return response
@app.get("/health")
def health():
    try:
        with get_conn() as conn: conn.execute("SELECT 1")
        status = "UP"
    except Exception: status = "DOWN"
    return {"service": SERVICE_NAME, "instance_id": f"{SERVICE_NAME}-{PORT}", "status": status, "db": status}
app.include_router(router)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
