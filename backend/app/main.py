"""Noka JUDGE FastAPI Application Entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.middleware.rate_limit import SecurityAndRateLimitMiddleware
from judge.sandbox.runner import cleanup_stale_exec_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_stale_exec_dirs()
    db = get_db()
    db.init_schema()
    yield
    cleanup_stale_exec_dirs()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityAndRateLimitMiddleware)
    app.include_router(api_router)

    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    return app


app = create_app()
