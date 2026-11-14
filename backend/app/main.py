"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ROUTERS, VERSION
from app.config import Settings, configure_logging, get_settings
from app.database.repository import Repository
from app.llm.service import LLMService
from app.simulation.engine import EngineError
from app.simulation.runtime import SimulationRuntime
from app.websocket.manager import ConnectionManager
from app.websocket.routes import router as ws_router

log = logging.getLogger("crisis_agents")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repo = Repository(settings.database_url)
        ws = ConnectionManager(settings.chat_message_delay_ms)
        ws.start()
        llm = LLMService(settings)
        app.state.repo, app.state.ws, app.state.llm = repo, ws, llm
        app.state.runtime = SimulationRuntime(settings, repo, ws, llm)
        log.info("CRISIS AGENTS backend ready (db=%s, llm=%s:%s)", settings.database_url.split("://")[0],
                 "groq" if llm.available else "deterministic-fallback", settings.groq_model)
        yield
        await app.state.runtime.shutdown()
        await ws.stop()

    app = FastAPI(title="CRISIS AGENTS API", version=VERSION, lifespan=lifespan,
                  description="Autonomous multi-agent negotiation for crisis resource allocation.")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

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

    for r in ROUTERS:
        app.include_router(r)
    app.include_router(ws_router)
    return app


app = create_app()
