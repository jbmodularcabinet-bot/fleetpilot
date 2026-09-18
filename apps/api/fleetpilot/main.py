import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from .adjustment_routes import router as adjustment_router
from .auth import auth, backend
from .config import get_settings
from .db import Session, engine
from .delivery_routes import router as delivery_router
from .evidence_storage import storage
from .expense_routes import router as expense_router
from .financial_routes import router as financial_router
from .governance_routes import router as governance_router
from .hardening import BodyLimitMiddleware, emit
from .maintenance_routes import router as maintenance_router
from .master_routes import router as master_router
from .rate_limits import category_for, consume
from .rate_limits import login_windows as login_windows
from .routes import router
from .s3_storage import StorageUnavailable
from .sync_routes import router as sync_router
from .trip_routes import router as trip_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    async with engine.connect() as connection:
        unsafe = await connection.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        if unsafe:
            raise RuntimeError("API must run with a non-superuser, NOBYPASSRLS role")
    if settings.environment == "production":
        await check_ready()
    yield
    await engine.dispose()


app = FastAPI(
    title="FleetPilot Foundation",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)
app.add_middleware(BodyLimitMiddleware)


def error_response(status: int, message: str, request: Request, code: str = "request_failed"):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


@app.middleware("http")
async def security_and_logging(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    started = time.monotonic()
    response = None
    try:
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin") != settings.web_origin
        ):
            response = error_response(
                403, "Request origin is not allowed.", request, "csrf_rejected"
            )
        category = category_for(request.method, request.url.path, settings)
        if response is None and category:
            # Trust ASGI peer only; ingress must overwrite forwarded headers and be explicitly trusted.
            identity = request.client.host if request.client else "unknown"
            try:
                allowed = await consume(
                    *category[:1], identity, category[1], settings.rate_limit_backend
                )
            except Exception:
                emit("rate_limit.failed", request_id=request.state.request_id)
                allowed = None
            if allowed is None:
                response = error_response(
                    503, "Request protection is unavailable. Please retry.", request
                )
            elif not allowed:
                response = error_response(
                    429, "Too many requests. Try again in one minute.", request, "rate_limited"
                )
                response.headers["Retry-After"] = "60"
        if response is None:
            response = await call_next(request)
    except StorageUnavailable:
        emit("storage.failed", request_id=request.state.request_id)
        response = error_response(503, "Evidence storage is unavailable. Please retry.", request)
    except Exception as exc:
        emit("request.failed", request_id=request.state.request_id, error_type=type(exc).__name__)
        response = error_response(
            500, "Something went wrong. Please retry.", request, "internal_error"
        )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; sandbox"
    )
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    route = getattr(request.scope.get("route"), "path", "unmatched")
    emit(
        "request.completed",
        request_id=request.state.request_id,
        route=route,
        method=request.method,
        status_code=response.status_code,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    messages = {
        "LOGIN_BAD_CREDENTIALS": "Email or password is incorrect.",
        "LOGIN_USER_NOT_VERIFIED": "Account is not verified.",
    }
    detail = str(getattr(exc.detail, "value", exc.detail))
    return error_response(exc.status_code, messages.get(detail, detail), request)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo submitted values, credentials, or validation internals.
    return error_response(
        422, "Check the submitted fields and try again.", request, "validation_error"
    )


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    return error_response(409, "The change conflicts with an existing record.", request, "conflict")


app.include_router(auth.get_auth_router(backend), prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(router)
app.include_router(master_router)
app.include_router(trip_router)
app.include_router(delivery_router)

app.include_router(sync_router)
app.include_router(expense_router)

app.include_router(adjustment_router)
app.include_router(maintenance_router)
app.include_router(financial_router)
app.include_router(governance_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


async def check_ready():
    settings.validate_runtime()
    async with Session() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0012_legacy_financial_review":
            raise RuntimeError("Database schema is incompatible")
        if settings.rate_limit_backend == "postgres":
            await session.execute(text("SELECT 1 FROM request_rate_windows LIMIT 1"))
    await run_in_threadpool(storage().health_check)


@app.get("/ready")
async def ready():
    try:
        await check_ready()
    except Exception:
        emit("readiness.failed")
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}
