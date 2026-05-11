"""SQLite database connection and operations.

Uses a simple in-process SQLite database with aiosqlite for async access.
All state lives in a single file; schema is auto-created on first use.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from evalarena.core.elo import ModelRating, update_ratings
from evalarena.db.models import (
    BattleCreate,
    BattleOut,
    LeaderboardEntry,
    ModelCreate,
    ModelOut,
    VoteCreate,
    Winner,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    rating      REAL NOT NULL DEFAULT 1000.0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    ties        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battles (
    id          TEXT PRIMARY KEY,
    model_a_id  TEXT NOT NULL REFERENCES models(id),
    model_b_id  TEXT NOT NULL REFERENCES models(id),
    prompt      TEXT NOT NULL,
    response_a  TEXT NOT NULL,
    response_b  TEXT NOT NULL,
    winner      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    id          TEXT PRIMARY KEY,
    battle_id   TEXT NOT NULL REFERENCES battles(id),
    winner      TEXT NOT NULL,
    voter_ip    TEXT,
    created_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open connection and ensure schema exists."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # ── Models CRUD ──────────────────────────────────────────────────

    async def create_model(self, data: ModelCreate) -> ModelOut:
        """Register a new model."""
        model_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO models (id, name, rating, wins, losses, ties, created_at) VALUES (?, ?, 1000.0, 0, 0, 0, ?)",
            (model_id, data.name, now),
        )
        await self.db.commit()
        return ModelOut(
            id=model_id,
            name=data.name,
            rating=1000.0,
            wins=0,
            losses=0,
            ties=0,
            total_games=0,
            win_rate=0.0,
        )

    async def get_model(self, model_id: str) -> ModelOut | None:
        """Get a model by ID."""
        async with self.db.execute("SELECT * FROM models WHERE id = ?", (model_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    async def get_model_by_name(self, name: str) -> ModelOut | None:
        """Get a model by name."""
        async with self.db.execute("SELECT * FROM models WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    async def list_models(self) -> list[ModelOut]:
        """List all registered models."""
        async with self.db.execute("SELECT * FROM models ORDER BY rating DESC") as cur:
            rows = await cur.fetchall()
            return [self._row_to_model(r) for r in rows]

    async def delete_model(self, model_id: str) -> bool:
        """Delete a model. Returns True if found and deleted."""
        async with self.db.execute("SELECT id FROM models WHERE id = ?", (model_id,)) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await self.db.commit()
        return True

    async def _update_model_rating(self, model_id: str, rating: ModelRating) -> None:
        """Update a model's ELO stats in the database."""
        await self.db.execute(
            "UPDATE models SET rating = ?, wins = ?, losses = ?, ties = ? WHERE id = ?",
            (rating.rating, rating.wins, rating.losses, rating.ties, model_id),
        )
        await self.db.commit()

    def _row_to_model(self, row: aiosqlite.Row) -> ModelOut:
        total = row["wins"] + row["losses"] + row["ties"]
        wr = (row["wins"] / total * 100) if total > 0 else 0.0
        return ModelOut(
            id=row["id"],
            name=row["name"],
            rating=row["rating"],
            wins=row["wins"],
            losses=row["losses"],
            ties=row["ties"],
            total_games=total,
            win_rate=round(wr, 1),
        )

    # ── Battles CRUD ─────────────────────────────────────────────────

    async def create_battle(self, data: BattleCreate) -> BattleOut:
        """Create a new blind battle."""
        battle_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO battles (id, model_a_id, model_b_id, prompt, response_a, response_b, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (battle_id, data.model_a_id, data.model_b_id, data.prompt, data.response_a, data.response_b, now),
        )
        await self.db.commit()
        return BattleOut(
            id=battle_id,
            prompt=data.prompt,
            response_a=data.response_a,
            response_b=data.response_b,
            created_at=now,
        )

    async def get_battle(self, battle_id: str) -> dict | None:
        """Get full battle data including model IDs and winner."""
        async with self.db.execute("SELECT * FROM battles WHERE id = ?", (battle_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def list_battles(self, limit: int = 20, offset: int = 0) -> list[BattleOut]:
        """List recent battles (blind)."""
        async with self.db.execute(
            "SELECT * FROM battles ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ) as cur:
            rows = await cur.fetchall()
            return [
                BattleOut(
                    id=r["id"],
                    prompt=r["prompt"],
                    response_a=r["response_a"],
                    response_b=r["response_b"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    async def set_battle_winner(self, battle_id: str, winner: str) -> None:
        """Record the winner of a battle."""
        await self.db.execute(
            "UPDATE battles SET winner = ? WHERE id = ?", (winner, battle_id)
        )
        await self.db.commit()

    # ── Votes CRUD ───────────────────────────────────────────────────

    async def create_vote(self, data: VoteCreate, voter_ip: str | None = None) -> bool:
        """Submit a vote and update ELO ratings.

        Returns True if the vote was recorded. Returns False if battle already voted on.
        """
        # Check battle exists and hasn't been voted on
        battle = await self.get_battle(data.battle_id)
        if not battle:
            raise ValueError(f"Battle {data.battle_id} not found")
        if battle["winner"] is not None:
            return False

        vote_id = _uuid()
        now = _now()

        # Record vote
        await self.db.execute(
            "INSERT INTO votes (id, battle_id, winner, voter_ip, created_at) VALUES (?, ?, ?, ?, ?)",
            (vote_id, data.battle_id, data.winner.value, voter_ip, now),
        )

        # Mark battle winner
        await self.set_battle_winner(data.battle_id, data.winner.value)

        # Update ELO ratings
        model_a = await self._get_rating(battle["model_a_id"])
        model_b = await self._get_rating(battle["model_b_id"])

        if data.winner == Winner.TIE:
            update_ratings(model_a, model_b, data.battle_id, is_tie=True)
        elif data.winner == Winner.MODEL_A:
            update_ratings(model_a, model_b, data.battle_id)
        else:
            update_ratings(model_b, model_a, data.battle_id)

        await self._update_model_rating(battle["model_a_id"], model_a)
        await self._update_model_rating(battle["model_b_id"], model_b)

        await self.db.commit()
        return True

    async def _get_rating(self, model_id: str) -> ModelRating:
        """Load a ModelRating from the database."""
        async with self.db.execute("SELECT * FROM models WHERE id = ?", (model_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise ValueError(f"Model {model_id} not found")
            return ModelRating(
                name=row["name"],
                rating=row["rating"],
                wins=row["wins"],
                losses=row["losses"],
                ties=row["ties"],
            )

    # ── Leaderboard ──────────────────────────────────────────────────

    async def get_leaderboard(self, limit: int = 50, offset: int = 0) -> list[LeaderboardEntry]:
        """Get ranked leaderboard."""
        entries: list[LeaderboardEntry] = []
        rank = offset + 1
        async with self.db.execute(
            "SELECT * FROM models ORDER BY rating DESC LIMIT ? OFFSET ?", (limit, offset)
        ) as cur:
            async for row in cur:
                total = row["wins"] + row["losses"] + row["ties"]
                wr = (row["wins"] / total * 100) if total > 0 else 0.0
                entries.append(
                    LeaderboardEntry(
                        rank=rank,
                        model_id=row["id"],
                        name=row["name"],
                        rating=round(row["rating"], 1),
                        wins=row["wins"],
                        losses=row["losses"],
                        ties=row["ties"],
                        total_games=total,
                        win_rate=round(wr, 1),
                    )
                )
                rank += 1
        return entries

    async def count_models(self) -> int:
        """Total number of registered models."""
        async with self.db.execute("SELECT COUNT(*) FROM models") as cur:
            row = await cur.fetchone()
            return row[0]

    async def count_battles(self) -> int:
        """Total number of battles."""
        async with self.db.execute("SELECT COUNT(*) FROM battles") as cur:
            row = await cur.fetchone()
            return row[0]
