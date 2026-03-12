"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from symphony.config import Config, get_config

if TYPE_CHECKING:
    from symphony.orchestrator import Orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    orchestrator: Orchestrator | None = app.state.orchestrator
    if orchestrator:
        await orchestrator.start()

    yield

    # Shutdown
    if orchestrator:
        await orchestrator.stop()


def create_app(
    config: Config | None = None,
    orchestrator: Orchestrator | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Configuration instance
        orchestrator: Orchestrator instance

    Returns:
        Configured FastAPI application
    """
    config = config or get_config()

    app = FastAPI(
        title="Symphony",
        description="Long-running automation service for coding agents",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store state
    app.state.config = config
    app.state.orchestrator = orchestrator

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    from symphony.server.routes import router
    app.include_router(router, prefix="/api/v1")

    # Health check
    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    return app
