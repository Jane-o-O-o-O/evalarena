"""FastAPI application factory.

Creates and configures the EvalArena web application with all API routes,
static files, Jinja2 templates, and rate limiting middleware.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from evalarena.db.database import Database

TEMPLATE_DIR = Path(__file__).parent / "templates"


# -- Rate Limiter -----------------------------------------------------------


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from `key` is allowed."""
        now = time.time()
        cutoff = now - self.window
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True


def create_app(
    db_path: str = "evalarena.db",
    in_memory: bool = False,
    rate_limit: int = 60,
    rate_window: int = 60,
    api_key: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database file.
        in_memory: If True, use in-memory database (for testing).
        rate_limit: Max requests per window per IP. Default 60/min.
        rate_window: Rate limit window in seconds. Default 60.
        api_key: If set, require this key for write operations (POST/PUT/DELETE).

    Returns:
        Configured FastAPI instance.
    """
    db = Database(":memory:" if in_memory else db_path)
    limiter = RateLimiter(max_requests=rate_limit, window_seconds=rate_window)

    # Closure-based accessor -- no global variable needed
    def get_db() -> Database:
        """Get the shared database instance."""
        return db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        yield
        await db.close()

    app = FastAPI(
        title="EvalArena",
        description="LLM Evaluation Arena",
        version="0.3.0",
        lifespan=lifespan,
    )

    # Store reference on app state for external access (tests, middleware)
    app.state.db = db

    # -- Rate limiting middleware ------------------------------------------

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting to API endpoints."""
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"
            if not limiter.is_allowed(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                )
        return await call_next(request)

    # -- API key auth middleware -------------------------------------------

    if api_key:
        WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

        @app.middleware("http")
        async def api_key_middleware(request: Request, call_next):
            """Require API key for write operations when configured."""
            if (
                request.url.path.startswith("/api/")
                and request.method in WRITE_METHODS
                and not request.url.path.startswith("/api/keys")
            ):
                provided = request.headers.get("X-API-Key", "")
                if provided != api_key:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing API key. Set X-API-Key header."},
                    )
            return await call_next(request)

    # Wire dependency injection in all route modules
    import evalarena.api.models as models_api
    import evalarena.api.arena as arena_api
    import evalarena.api.vote as vote_api
    import evalarena.api.leaderboard as lb_api
    import evalarena.api.stats as stats_api
    import evalarena.api.keys as keys_api

    for mod in [models_api, arena_api, vote_api, lb_api, stats_api, keys_api]:
        mod.get_db = get_db

    # Register routers
    from evalarena.api.models import router as models_router
    from evalarena.api.arena import router as arena_router
    from evalarena.api.vote import router as vote_router
    from evalarena.api.leaderboard import router as leaderboard_router
    from evalarena.api.stats import router as stats_router
    from evalarena.api.keys import router as keys_router

    app.include_router(models_router)
    app.include_router(arena_router)
    app.include_router(vote_router)
    app.include_router(leaderboard_router)
    app.include_router(stats_router)
    app.include_router(keys_router)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.3.0"}

    # Web UI routes (Jinja2 templates)
    if TEMPLATE_DIR.exists():
        templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

        @app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            """Landing page with platform overview."""
            stats = await db.get_stats()
            leaderboard = await db.get_leaderboard(limit=5)
            return templates.TemplateResponse(
                request, "index.html", {"stats": stats, "leaderboard": leaderboard}
            )

        @app.get("/arena", response_class=HTMLResponse)
        async def arena_page(request: Request):
            """Arena voting page."""
            leaderboard = await db.get_leaderboard(limit=10)
            return templates.TemplateResponse(
                request, "arena.html", {"leaderboard": leaderboard}
            )

        @app.get("/leaderboard", response_class=HTMLResponse)
        async def leaderboard_page(request: Request, category: str | None = None):
            """Full leaderboard page."""
            entries = await db.get_leaderboard(limit=100, category=category)
            categories = await db.list_categories()
            return templates.TemplateResponse(
                request,
                "leaderboard.html",
                {
                    "entries": entries,
                    "total": len(entries),
                    "categories": categories,
                    "selected_category": category,
                },
            )

        @app.get("/model/{model_id}", response_class=HTMLResponse)
        async def model_detail_page(request: Request, model_id: str):
            """Model detail page with match history."""
            detail = await db.get_model_detail(model_id)
            if not detail:
                return templates.TemplateResponse(
                    request, "404.html", {"message": "Model not found"}, status_code=404
                )
            return templates.TemplateResponse(
                request, "model_detail.html", {"model": detail}
            )

        @app.get("/compare", response_class=HTMLResponse)
        async def compare_page(request: Request):
            """Head-to-head comparison page."""
            models = await db.list_models()
            return templates.TemplateResponse(
                request, "compare.html", {"models": models}
            )

    return app
