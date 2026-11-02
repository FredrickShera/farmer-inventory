"""Application factory. Dependencies are injected so tests can run without Supabase.

Run with:  uvicorn app.main:create_app --factory
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth_gateway import AuthGateway, SupabaseAuthGateway
from .config import Settings, get_settings
from .errors import install_error_handlers
from .repository import PostgresRepository, Repository
from .routers import auth, farmers, inventory, lookups
from .security import TokenVerifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(settings: Settings | None = None, *, repo: Repository | None = None,
               gateway: AuthGateway | None = None, verifier: TokenVerifier | None = None) -> FastAPI:
    settings = settings or get_settings()
    owns_repo = repo is None
    repo = repo or PostgresRepository(settings.database_url, settings.db_pool_max)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if owns_repo:
            repo.open()  # type: ignore[attr-defined]
        yield
        if owns_repo:
            repo.close()  # type: ignore[attr-defined]

    app = FastAPI(title="Farmer Cooperative API", version="1.0.0", lifespan=lifespan,
                  description="Farmer registration and produce inventory. Auth: Supabase JWT, verified here.")
    app.state.settings = settings
    app.state.repo = repo
    app.state.gateway = gateway or SupabaseAuthGateway(settings)
    app.state.verifier = verifier or TokenVerifier(settings)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    for r in (lookups.router, auth.router, farmers.router, inventory.router):
        app.include_router(r)
    return app
