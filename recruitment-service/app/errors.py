import logging, uuid
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
class ApiError(Exception):
    def __init__(self, status_code, code, message, details=None): self.status_code, self.code, self.message, self.details = status_code, code, message, details or {}
def respond(request, status, code, message, details=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", str(uuid.uuid4())), "details": details or {}}})
async def api_error_handler(request: Request, exc: ApiError): return respond(request, exc.status_code, exc.code, exc.message, exc.details)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    problems = [{"field": ".".join(str(p) for p in error["loc"] if p != "body"), "issue": error["msg"]} for error in exc.errors()]
    return respond(request, 400, "VALIDATION_ERROR", "Request validation failed", {"problems": problems})
async def http_exception_handler(request: Request, exc: HTTPException): return respond(request, exc.status_code, "METHOD_NOT_ALLOWED" if exc.status_code == 405 else "NOT_FOUND", str(exc.detail))
async def generic_exception_handler(request: Request, exc: Exception): logging.exception("Unhandled error"); return respond(request, 500, "INTERNAL_ERROR", "Internal server error")
