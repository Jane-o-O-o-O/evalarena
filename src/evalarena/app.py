"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="EvalArena",
        description="LLM Evaluation Arena",
        version="0.1.0",
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
