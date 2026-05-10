"""Shared test fixtures for EvalArena."""
import pytest
import pytest_asyncio
from pathlib import Path

from evalarena.db.database import init_db, close_db


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test_evalarena.db"
    conn = await init_db(db_path)
    yield conn
    await close_db()


@pytest.fixture
def sample_model_data():
    """Sample model registration data."""
    return {
        "name": "gpt-4o",
        "organization": "OpenAI",
        "description": "GPT-4 Omni model",
    }
