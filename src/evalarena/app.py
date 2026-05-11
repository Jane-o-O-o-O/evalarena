"""FastAPI application factory.

Creates and configures the EvalArena web application with all API routes,
static files, and Jinja2 templates.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from evalarena.db.database import Database

# Shared database instance
_db: Database | None = None

TEMPLATE_DIR = Path(__file__).parent / "templates"


def get_db() -> Database:
    """Get the shared database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def create_app(db_path: str = "evalarena.db", in_memory: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file.
        in_memory: If True, use in-memory database (for testing).

    Returns:
        Configured FastAPI instance.
    """
    global _db
    _db = Database(":memory:" if in_memory else db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _db.connect()
        yield
        await _db.close()

    app = FastAPI(
        title="EvalArena",
        description="LLM 评估竞技场 — 盲评侧边对比，ELO 排行榜",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Override get_db dependency in all route modules
    import evalarena.api.models as models_api
    import evalarena.api.arena as arena_api
    import evalarena.api.vote as vote_api
    import evalarena.api.leaderboard as lb_api

    models_api.get_db = get_db
    arena_api.get_db = get_db
    vote_api.get_db = get_db
    lb_api.get_db = get_db

    # Register routers
    from evalarena.api.models import router as models_router
    from evalarena.api.arena import router as arena_router
    from evalarena.api.vote import router as vote_router
    from evalarena.api.leaderboard import router as leaderboard_router

    app.include_router(models_router)
    app.include_router(arena_router)
    app.include_router(vote_router)
    app.include_router(leaderboard_router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Web UI routes (Jinja2 templates)
    if TEMPLATE_DIR.exists():
        templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

        @app.get("/", response_class=HTMLResponse)
        async def index():
            """Landing page — redirect to arena."""
            return '<html><head><meta http-equiv="refresh" content="0;url=/arena"></head></html>'

        @app.get("/arena", response_class=HTMLResponse)
        async def arena_page(request):
            """Arena voting page."""
            battles = await _db.list_battles(limit=1)
            leaderboard = await _db.get_leaderboard(limit=10)
            return templates.TemplateResponse("arena.html", {
                "request": request,
                "battles": battles,
                "leaderboard": leaderboard,
            })

        @app.get("/leaderboard", response_class=HTMLResponse)
        async def leaderboard_page(request):
            """Full leaderboard page."""
            entries = await _db.get_leaderboard(limit=100)
            return templates.TemplateResponse("leaderboard.html", {
                "request": request,
                "entries": entries,
                "total": len(entries),
            })

    return app
