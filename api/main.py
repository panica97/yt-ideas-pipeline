"""FastAPI application — IRT Dashboard API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.middleware.auth import ApiKeyMiddleware
from api.routers import channels, export, health, history, instruments, research, stats, strategies, topics
from api.services.research_watcher import ResearchWatcher

logger = logging.getLogger(__name__)

# Shared watcher instance
_watcher: ResearchWatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _watcher

    # Startup: initialize ResearchWatcher LISTEN
    _watcher = ResearchWatcher()
    research.set_watcher(_watcher)
    await _watcher.start()
    logger.info("IRT API started — ResearchWatcher active")

    yield

    # Shutdown: cleanup
    if _watcher:
        await _watcher.stop()
    logger.info("IRT API stopped")


app = FastAPI(
    title="IRT Dashboard API",
    description="API para el dashboard del pipeline de investigacion de trading",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware (order matters: outermost runs first) ---

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key auth (applied after CORS so pre-flight OPTIONS pass through)
app.add_middleware(ApiKeyMiddleware)

# --- Routers ---
app.include_router(health.router)
app.include_router(topics.router)
app.include_router(channels.router)
app.include_router(strategies.router)
app.include_router(history.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(instruments.router)
app.include_router(research.router)
