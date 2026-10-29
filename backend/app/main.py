"""FastAPI entrypoint for the SWARM EVOLVE-X experiment service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import Settings
from app.storage.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or Settings()
    app = FastAPI(
        title="SWARM EVOLVE-X AI",
        version="1.0.0",
        summary="Typed experiment API for failure-seeking gripper and energy search.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = active
    app.state.db = Database(active.resolved_database_url())
    app.state.db.init()
    app.state.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="swarm-run")
    app.include_router(router)
    return app


app = create_app()
