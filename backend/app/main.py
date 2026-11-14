"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes
from app.api.auth import ADMIN, COMMANDER, VIEWER, TokenRegistry
from app.config import Settings, configure_logging, get_settings
from app.database.repository import Repository
from app.llm.service import LLMService
from app.schemas.api import ErrorResponse
from app.simulation.engine import EngineError
from app.simulation.runtime import RunManager
from app.websocket.routes import router as ws_router

log = logging.getLogger("crisis_agents")


class BodySizeLimit:
    """Reject request bodies above ``max_bytes`` (413), including chunked bodies without Content-Length."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            return await self._reject(send)
        seen = 0

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _TooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = b'{"error":{"code":"PAYLOAD_TOO_LARGE","message":"request body too large"}}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repo = Repository(settings.database_url, settings.auto_create_schema)
        llm = LLMService(settings)
        runs = RunManager(settings, repo, llm)
        await runs.start()
        app.state.repo, app.state.llm, app.state.runs = repo, llm, runs
        log.info("CRISIS AGENTS backend ready (env=%s, db=%s, llm=%s:%s, test_routes=%s, viewer_public=%s)",
                 settings.env, settings.database_url.split("://")[0],
                 "groq" if llm.available else "deterministic-fallback", settings.groq_model,
                 settings.test_routes_enabled, app.state.tokens.public_read)
        yield
        await runs.shutdown()

    app = FastAPI(title="CRISIS AGENTS API", version=routes.VERSION, lifespan=lifespan,
                  description="Autonomous multi-agent negotiation for crisis resource allocation. "
                              "Send `Authorization: Bearer <token>`; roles: viewer < commander < admin.")
    app.state.settings = settings
    app.state.tokens = TokenRegistry(settings)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes)

    @app.exception_handler(EngineError)
    async def engine_error(_: Request, exc: EngineError):
        return JSONResponse(status_code=exc.status,
                            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {
            "code": "INVALID_REQUEST", "message": "request validation failed",
            "details": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR",
                                                                "message": "internal server error"}})

    @app.get("/healthz", include_in_schema=False)
    async def liveness():
        return {"status": "ok"}

    # Router-level role dependencies: every route inherits its router's protection (F2).
    groups = [(routes.read, VIEWER), (routes.control, COMMANDER), (routes.admin, ADMIN)]
    if settings.test_routes_enabled:
        groups.append((routes.test, ADMIN))
    scoped = [Depends(routes.run_id_param)]
    # Document the real error envelope (replaces FastAPI's default {"detail": [...]} 422 schema).
    errors = {code: {"model": ErrorResponse, "description": desc} for code, desc in (
        (403, "Missing or invalid bearer token, or insufficient role"),
        (404, "Unknown run, agent, proposal, incident or alert"),
        (409, "Not allowed in the current state (e.g. ALREADY_RUNNING, NOT_PAUSED, VALIDATION_FAILED)"),
        (422, "Request validation failed"))}
    for router, role in groups:
        app.include_router(router, prefix="/api", dependencies=[Depends(role)], responses=errors)
        app.include_router(router, prefix="/api/runs/{run_id}", dependencies=[Depends(role), *scoped],
                           responses=errors)
    app.include_router(routes.runs_read, dependencies=[Depends(VIEWER)], responses=errors)
    app.include_router(routes.runs_control, dependencies=[Depends(COMMANDER)], responses=errors)
    app.include_router(routes.runs_admin, dependencies=[Depends(ADMIN)], responses=errors)
    app.include_router(routes.metrics_router, dependencies=[Depends(VIEWER)])
    app.include_router(ws_router)
    return app


app = create_app()
