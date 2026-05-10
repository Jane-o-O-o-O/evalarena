"""Database connection and session management using aiosqlite."""
import aiosqlite
from pathlib import Path

DEFAULT_DB_PATH = Path("evalarena.db")

_db_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the active database connection."""
    if _db_connection is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_connection


async def init_db(db_path: Path | str | None = None) -> aiosqlite.Connection:
    """Initialize the database with schema."""
    global _db_connection
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    _db_connection = await aiosqlite.connect(str(path))
    _db_connection.row_factory = aiosqlite.Row
    await _db_connection.execute("PRAGMA journal_mode=WAL")
    await _db_connection.execute("PRAGMA foreign_keys=ON")
    await _run_migrations(_db_connection)
    return _db_connection


async def close_db() -> None:
    """Close the database connection."""
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None


async def _run_migrations(conn: aiosqlite.Connection) -> None:
    """Run all database migrations."""
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            organization TEXT,
            description TEXT,
            elo_rating REAL NOT NULL DEFAULT 1000.0,
            games_played INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            ties INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_a_id INTEGER NOT NULL,
            model_b_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            model_a_response TEXT NOT NULL,
            model_b_response TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'voted')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_a_id) REFERENCES models(id),
            FOREIGN KEY (model_b_id) REFERENCES models(id)
        );

        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battle_id INTEGER NOT NULL,
            winner TEXT NOT NULL CHECK(winner IN ('model_a', 'model_b', 'tie')),
            voter_ip TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (battle_id) REFERENCES battles(id)
        );

        CREATE INDEX IF NOT EXISTS idx_battles_status ON battles(status);
        CREATE INDEX IF NOT EXISTS idx_models_elo ON models(elo_rating DESC);
        CREATE INDEX IF NOT EXISTS idx_votes_battle ON votes(battle_id);
    """)
    await conn.commit()
