"""FastAPI application factory."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from evalarena.db.database import init_db, close_db
from evalarena.api.models import router as models_router
from evalarena.api.leaderboard import router as leaderboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="EvalArena",
        description="LLM Evaluation Arena - Side-by-side model comparison with ELO ratings",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register API routes
    app.include_router(models_router)
    app.include_router(leaderboard_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
