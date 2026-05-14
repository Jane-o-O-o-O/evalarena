"""SQLite database connection and operations.

Uses a simple in-process SQLite database with aiosqlite for async access.
All state lives in a single file; schema is auto-created on first use.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from evalarena.core.elo import ModelRating, update_ratings, rating_confidence_interval
from evalarena.db.models import (
    BatchBattleCreate,
    BatchBattleOut,
    BattleCreate,
    BattleOut,
    BattleSummary,
    HeadToHead,
    LeaderboardEntry,
    ModelCreate,
    ModelDetail,
    ModelOut,
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplateUpdate,
    StatsOut,
    VoteCreate,
    Winner,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    category        TEXT NOT NULL DEFAULT 'general',
    description     TEXT NOT NULL DEFAULT '',
    organization    TEXT NOT NULL DEFAULT '',
    parameter_count TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL DEFAULT '',
    api_model_id    TEXT NOT NULL DEFAULT '',
    rating          REAL NOT NULL DEFAULT 1000.0,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    ties            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS api_keys (
    key         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    prompt_text  TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT 'general',
    description  TEXT NOT NULL DEFAULT '',
    usage_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tournaments (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    category         TEXT NOT NULL DEFAULT 'general',
    prompts_per_match INTEGER NOT NULL DEFAULT 1,
    prompt_template_id TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tournament_models (
    tournament_id TEXT NOT NULL REFERENCES tournaments(id),
    model_id      TEXT NOT NULL REFERENCES models(id),
    PRIMARY KEY (tournament_id, model_id)
);

CREATE TABLE IF NOT EXISTS tournament_matches (
    id              TEXT PRIMARY KEY,
    tournament_id   TEXT NOT NULL REFERENCES tournaments(id),
    model_a_id      TEXT NOT NULL REFERENCES models(id),
    model_b_id      TEXT NOT NULL REFERENCES models(id),
    winner_model_id TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tournament_match_battles (
    match_id  TEXT NOT NULL REFERENCES tournament_matches(id),
    battle_id TEXT NOT NULL REFERENCES battles(id),
    PRIMARY KEY (match_id, battle_id)
);

CREATE TABLE IF NOT EXISTS webhooks (
    id         TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    event      TEXT NOT NULL DEFAULT 'vote',
    secret     TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT NOT NULL DEFAULT '#6366f1',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_tags (
    model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    tag_id   TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, tag_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '',
    actor_ip    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vote_dimensions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id         TEXT NOT NULL REFERENCES votes(id),
    dimension_name  TEXT NOT NULL,
    score           INTEGER NOT NULL
);"""


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
        # Migration: add category column if upgrading from older schema
        try:
            await self._db.execute(
                "ALTER TABLE models ADD COLUMN category TEXT NOT NULL DEFAULT 'general'"
            )
        except Exception:
            pass  # Column already exists
        # Migration: add model metadata columns
        for col in [
            "description TEXT NOT NULL DEFAULT ''",
            "organization TEXT NOT NULL DEFAULT ''",
            "parameter_count TEXT NOT NULL DEFAULT ''",
            "provider TEXT NOT NULL DEFAULT ''",
            "api_model_id TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                await self._db.execute(f"ALTER TABLE models ADD COLUMN {col}")
            except Exception:
                pass  # Column already exists
        # Migration: add rating tracking columns to battles
        for col in [
            "model_a_rating_before REAL",
            "model_b_rating_before REAL",
            "model_a_rating_after REAL",
            "model_b_rating_after REAL",
        ]:
            try:
                await self._db.execute(f"ALTER TABLE battles ADD COLUMN {col}")
            except Exception:
                pass  # Column already exists
        # Migration: add comment column to votes
        try:
            await self._db.execute("ALTER TABLE votes ADD COLUMN comment TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # Column already exists
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

    # -- Models CRUD -----------------------------------------------------

    async def create_model(self, data: ModelCreate) -> ModelOut:
        """Register a new model."""
        model_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO models (id, name, category, description, organization, parameter_count, "
            "provider, api_model_id, rating, wins, losses, ties, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1000.0, 0, 0, 0, ?)",
            (model_id, data.name, data.category, data.description,
             data.organization, data.parameter_count, data.provider,
             data.api_model_id, now),
        )
        await self.db.commit()
        return ModelOut(
            id=model_id,
            name=data.name,
            category=data.category,
            description=data.description,
            organization=data.organization,
            parameter_count=data.parameter_count,
            provider=data.provider,
            api_model_id=data.api_model_id,
            rating=1000.0,
            wins=0,
            losses=0,
            ties=0,
            total_games=0,
            win_rate=0.0,
            ci_lower=600.0,
            ci_upper=1400.0,
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

    async def list_models(self, category: str | None = None) -> list[ModelOut]:
        """List all registered models, optionally filtered by category."""
        if category:
            async with self.db.execute(
                "SELECT * FROM models WHERE category = ? ORDER BY rating DESC", (category,)
            ) as cur:
                rows = await cur.fetchall()
        else:
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

    async def update_model(self, model_id: str, data: "ModelUpdate") -> ModelOut | None:
        """Update a model's metadata fields.

        Only non-None fields in ``data`` are updated.

        Args:
            model_id: The model to update.
            data: Partial update data.

        Returns:
            Updated ModelOut, or None if model not found.
        """
        from evalarena.db.models import ModelUpdate

        existing = await self.get_model(model_id)
        if not existing:
            return None

        # Build SET clause from non-None fields
        updates: list[str] = []
        params: list = []
        for field_name in [
            "name", "category", "description", "organization",
            "parameter_count", "provider", "api_model_id",
        ]:
            value = getattr(data, field_name, None)
            if value is not None:
                updates.append(f"{field_name} = ?")
                params.append(value)

        if not updates:
            return existing  # Nothing to update

        params.append(model_id)
        sql = f"UPDATE models SET {', '.join(updates)} WHERE id = ?"
        await self.db.execute(sql, params)
        await self.db.commit()
        return await self.get_model(model_id)

    async def _update_model_rating(self, model_id: str, rating: ModelRating) -> None:
        """Update a model\'s ELO stats in the database."""
        await self.db.execute(
            "UPDATE models SET rating = ?, wins = ?, losses = ?, ties = ? WHERE id = ?",
            (rating.rating, rating.wins, rating.losses, rating.ties, model_id),
        )
        await self.db.commit()

    def _row_to_model(self, row: aiosqlite.Row) -> ModelOut:
        total = row["wins"] + row["losses"] + row["ties"]
        wr = (row["wins"] / total * 100) if total > 0 else 0.0
        ci_lo, ci_hi = rating_confidence_interval(row["rating"], total)
        keys = row.keys()
        return ModelOut(
            id=row["id"],
            name=row["name"],
            category=row["category"] if "category" in keys else "general",
            description=row["description"] if "description" in keys else "",
            organization=row["organization"] if "organization" in keys else "",
            parameter_count=row["parameter_count"] if "parameter_count" in keys else "",
            provider=row["provider"] if "provider" in keys else "",
            api_model_id=row["api_model_id"] if "api_model_id" in keys else "",
            rating=row["rating"],
            wins=row["wins"],
            losses=row["losses"],
            ties=row["ties"],
            total_games=total,
            win_rate=round(wr, 1),
            ci_lower=ci_lo,
            ci_upper=ci_hi,
        )

    # -- Battles CRUD ----------------------------------------------------

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
            voted=False,
            created_at=now,
        )

    async def get_battle(self, battle_id: str) -> dict | None:
        """Get full battle data including model IDs and winner."""
        async with self.db.execute("SELECT * FROM battles WHERE id = ?", (battle_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def list_battles(self, limit: int = 20, offset: int = 0, unvoted_only: bool = False) -> list[BattleOut]:
        """List recent battles (blind)."""
        if unvoted_only:
            query = "SELECT * FROM battles WHERE winner IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?"
        else:
            query = "SELECT * FROM battles ORDER BY created_at DESC LIMIT ? OFFSET ?"
        async with self.db.execute(query, (limit, offset)) as cur:
            rows = await cur.fetchall()
            return [
                BattleOut(
                    id=r["id"],
                    prompt=r["prompt"],
                    response_a=r["response_a"],
                    response_b=r["response_b"],
                    voted=r["winner"] is not None,
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

    # -- Votes CRUD ------------------------------------------------------

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

    # -- Leaderboard -----------------------------------------------------

    async def get_leaderboard(
        self, limit: int = 50, offset: int = 0, category: str | None = None
    ) -> list[LeaderboardEntry]:
        """Get ranked leaderboard, optionally filtered by category."""
        entries: list[LeaderboardEntry] = []
        rank = offset + 1
        if category:
            query = (
                "SELECT * FROM models WHERE category = ? ORDER BY rating DESC LIMIT ? OFFSET ?"
            )
            params = (category, limit, offset)
        else:
            query = "SELECT * FROM models ORDER BY rating DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        async with self.db.execute(query, params) as cur:
            async for row in cur:
                total = row["wins"] + row["losses"] + row["ties"]
                wr = (row["wins"] / total * 100) if total > 0 else 0.0
                ci_lo, ci_hi = rating_confidence_interval(row["rating"], total)
                entries.append(
                    LeaderboardEntry(
                        rank=rank,
                        model_id=row["id"],
                        name=row["name"],
                        category=row["category"] if "category" in row.keys() else "general",
                        rating=round(row["rating"], 1),
                        wins=row["wins"],
                        losses=row["losses"],
                        ties=row["ties"],
                        total_games=total,
                        win_rate=round(wr, 1),
                        ci_lower=ci_lo,
                        ci_upper=ci_hi,
                    )
                )
                rank += 1
        return entries

    async def list_categories(self) -> list[str]:
        """List all distinct categories in use."""
        async with self.db.execute(
            "SELECT DISTINCT category FROM models ORDER BY category"
        ) as cur:
            rows = await cur.fetchall()
            return [r["category"] for r in rows]

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

    async def count_votes(self) -> int:
        """Total number of votes."""
        async with self.db.execute("SELECT COUNT(*) FROM votes") as cur:
            row = await cur.fetchone()
            return row[0]

    # -- Match History ---------------------------------------------------

    async def get_model_battles(
        self, model_id: str, limit: int = 20, offset: int = 0
    ) -> list[BattleSummary]:
        """Get all battles involving a model, most recent first.

        Returns BattleSummary objects with opponent name and result.
        """
        summaries: list[BattleSummary] = []
        async with self.db.execute(
            "SELECT b.*, "
            "ma.name as name_a, mb.name as name_b "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "WHERE b.model_a_id = ? OR b.model_b_id = ? "
            "ORDER BY b.created_at DESC LIMIT ? OFFSET ?",
            (model_id, model_id, limit, offset),
        ) as cur:
            async for row in cur:
                is_model_a = row["model_a_id"] == model_id
                opponent_name = row["name_b"] if is_model_a else row["name_a"]
                prompt_short = row["prompt"][:80] + ("..." if len(row["prompt"]) > 80 else "")

                if row["winner"] is None:
                    result = "pending"
                    rating_change = 0.0
                elif row["winner"] == "tie":
                    result = "tie"
                elif (row["winner"] == "model_a" and is_model_a) or (
                    row["winner"] == "model_b" and not is_model_a
                ):
                    result = "win"
                else:
                    result = "loss"

                # Compute rating change from stored before/after values
                if row["winner"] is not None:
                    rating_change = 0.0
                    keys = row.keys()
                    if "model_a_rating_before" in keys and row["model_a_rating_before"] is not None:
                        if is_model_a:
                            rating_change = round(row["model_a_rating_after"] - row["model_a_rating_before"], 1)
                        else:
                            rating_change = round(row["model_b_rating_after"] - row["model_b_rating_before"], 1)

                summaries.append(
                    BattleSummary(
                        id=row["id"],
                        prompt=prompt_short,
                        opponent_name=opponent_name,
                        result=result,
                        rating_change=rating_change,
                        created_at=row["created_at"],
                    )
                )
        return summaries

    # -- Head-to-Head ----------------------------------------------------

    async def head_to_head(self, model_a_id: str, model_b_id: str) -> HeadToHead:
        """Get head-to-head stats between two models."""
        model_a = await self.get_model(model_a_id)
        model_b = await self.get_model(model_b_id)
        if not model_a or not model_b:
            raise ValueError("One or both models not found")

        a_wins = 0
        b_wins = 0
        ties = 0

        async with self.db.execute(
            "SELECT winner, model_a_id FROM battles "
            "WHERE ((model_a_id = ? AND model_b_id = ?) OR (model_a_id = ? AND model_b_id = ?)) "
            "AND winner IS NOT NULL",
            (model_a_id, model_b_id, model_b_id, model_a_id),
        ) as cur:
            async for row in cur:
                if row["winner"] == "tie":
                    ties += 1
                elif (row["winner"] == "model_a" and row["model_a_id"] == model_a_id) or (
                    row["winner"] == "model_b" and row["model_a_id"] == model_b_id
                ):
                    a_wins += 1
                else:
                    b_wins += 1

        total = a_wins + b_wins + ties
        return HeadToHead(
            model_a=model_a.name,
            model_b=model_b.name,
            model_a_wins=a_wins,
            model_b_wins=b_wins,
            ties=ties,
            total_battles=total,
            model_a_win_rate=round(a_wins / total * 100, 1) if total > 0 else 0.0,
            model_a_rating_before=1000.0,
            model_a_rating_after=model_a.rating,
            model_b_rating_before=1000.0,
            model_b_rating_after=model_b.rating,
        )

    # -- Stats -----------------------------------------------------------

    async def get_stats(self) -> StatsOut:
        """Get aggregate platform statistics."""
        total_models = await self.count_models()
        total_battles = await self.count_battles()
        total_votes = await self.count_votes()

        # Avg, max, min ratings
        async with self.db.execute(
            "SELECT AVG(rating), MAX(rating), MIN(rating) FROM models"
        ) as cur:
            row = await cur.fetchone()
            avg_rating = round(row[0] or 0.0, 1)
            max_rating = round(row[1] or 0.0, 1)
            min_rating = round(row[2] or 0.0, 1)

        # Most active model (most battles)
        most_active = ""
        async with self.db.execute(
            "SELECT m.name, COUNT(*) as cnt FROM battles b "
            "JOIN models m ON m.id = b.model_a_id OR m.id = b.model_b_id "
            "GROUP BY m.id ORDER BY cnt DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if row:
                most_active = row[0]

        # Battles today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with self.db.execute(
            "SELECT COUNT(*) FROM battles WHERE created_at LIKE ?",
            (f"{today}%",),
        ) as cur:
            row = await cur.fetchone()
            battles_today = row[0]

        return StatsOut(
            total_models=total_models,
            total_battles=total_battles,
            total_votes=total_votes,
            avg_rating=avg_rating,
            highest_rating=max_rating,
            lowest_rating=min_rating,
            most_active_model=most_active,
            battles_today=battles_today,
        )

    # -- Model Detail ----------------------------------------------------

    async def get_model_detail(self, model_id: str) -> ModelDetail | None:
        """Get detailed model info with match history."""
        model = await self.get_model(model_id)
        if not model:
            return None

        async with self.db.execute(
            "SELECT created_at, description, organization, parameter_count FROM models WHERE id = ?",
            (model_id,),
        ) as cur:
            row = await cur.fetchone()
            created_at = row[0] if row else ""
            description = row[1] if row and len(row) > 1 else ""
            organization = row[2] if row and len(row) > 2 else ""
            parameter_count = row[3] if row and len(row) > 3 else ""

        recent_battles = await self.get_model_battles(model_id, limit=20)

        return ModelDetail(
            id=model.id,
            name=model.name,
            category=model.category,
            description=description,
            organization=organization,
            parameter_count=parameter_count,
            rating=model.rating,
            wins=model.wins,
            losses=model.losses,
            ties=model.ties,
            total_games=model.total_games,
            win_rate=model.win_rate,
            ci_lower=model.ci_lower,
            ci_upper=model.ci_upper,
            recent_battles=recent_battles,
            created_at=created_at,
        )

    # -- API Keys ----------------------------------------------------------

    async def create_api_key(self, key: str, name: str) -> str:
        """Create a new API key.

        Args:
            key: The API key string.
            name: Human-readable name/description for the key.

        Returns:
            The created key string.
        """
        now = _now()
        await self.db.execute(
            "INSERT INTO api_keys (key, name, active, created_at) VALUES (?, ?, 1, ?)",
            (key, name, now),
        )
        await self.db.commit()
        return key

    async def validate_api_key(self, key: str) -> bool:
        """Check if an API key is valid and active.

        Args:
            key: The API key to validate.

        Returns:
            True if the key exists and is active.
        """
        async with self.db.execute(
            "SELECT active FROM api_keys WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            return bool(row["active"])

    async def list_api_keys(self) -> list[dict]:
        """List all API keys (without exposing the actual key).

        Returns:
            List of dicts with name, active status, and created_at.
        """
        async with self.db.execute(
            "SELECT key, name, active, created_at FROM api_keys ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "key_prefix": r["key"][:8] + "...",
                    "name": r["name"],
                    "active": bool(r["active"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    async def deactivate_api_key(self, key: str) -> bool:
        """Deactivate an API key.

        Args:
            key: The API key to deactivate.

        Returns:
            True if the key was found and deactivated.
        """
        async with self.db.execute(
            "SELECT key FROM api_keys WHERE key = ?", (key,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute(
            "UPDATE api_keys SET active = 0 WHERE key = ?", (key,)
        )
        await self.db.commit()
        return True

    # -- Search -----------------------------------------------------------

    async def search_models(self, query: str, limit: int = 20) -> list[ModelOut]:
        """Search models by name or organization.

        Args:
            query: Search string (partial match on name or organization).
            limit: Max results to return.

        Returns:
            List of matching models sorted by rating.
        """
        pattern = f"%{query}%"
        async with self.db.execute(
            "SELECT * FROM models WHERE name LIKE ? OR organization LIKE ? "
            "ORDER BY rating DESC LIMIT ?",
            (pattern, pattern, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    # -- Rating History ---------------------------------------------------

    async def get_rating_history(
        self, model_id: str, limit: int = 50
    ) -> list["RatingHistoryEntry"]:
        """Get the rating history for a model across its battles.

        Returns a chronological list of rating snapshots after each battle.
        """
        from evalarena.db.models import RatingHistoryEntry

        entries: list[RatingHistoryEntry] = []
        async with self.db.execute(
            "SELECT b.id, b.model_a_id, b.model_b_id, b.winner, b.created_at, "
            "b.model_a_rating_after, b.model_b_rating_after, "
            "b.model_a_rating_before, b.model_b_rating_before, "
            "ma.name as name_a, mb.name as name_b "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "WHERE (b.model_a_id = ? OR b.model_b_id = ?) AND b.winner IS NOT NULL "
            "ORDER BY b.created_at ASC LIMIT ?",
            (model_id, model_id, limit),
        ) as cur:
            async for row in cur:
                is_model_a = row["model_a_id"] == model_id
                opponent = row["name_b"] if is_model_a else row["name_a"]

                if row["winner"] == "tie":
                    result = "tie"
                elif (row["winner"] == "model_a" and is_model_a) or (
                    row["winner"] == "model_b" and not is_model_a
                ):
                    result = "win"
                else:
                    result = "loss"

                if is_model_a:
                    rating_after = row["model_a_rating_after"] or 1000.0
                    rating_before = row["model_a_rating_before"] or 1000.0
                else:
                    rating_after = row["model_b_rating_after"] or 1000.0
                    rating_before = row["model_b_rating_before"] or 1000.0

                entries.append(
                    RatingHistoryEntry(
                        battle_id=row["id"],
                        rating=round(rating_after, 1),
                        rating_change=round(rating_after - rating_before, 1),
                        opponent_name=opponent,
                        result=result,
                        created_at=row["created_at"],
                    )
                )
        return entries

    # -- Battle Details ---------------------------------------------------

    async def get_battles_with_details(
        self, limit: int = 30, offset: int = 0
    ) -> list[dict]:
        """Get battles with model names and results revealed.

        Args:
            limit: Max battles to return.
            offset: Pagination offset.

        Returns:
            List of battle dicts with model names and winner info.
        """
        results: list[dict] = []
        async with self.db.execute(
            "SELECT b.*, ma.name as name_a, mb.name as name_b "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "ORDER BY b.created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            async for row in cur:
                winner_name = None
                if row["winner"] == "model_a":
                    winner_name = row["name_a"]
                elif row["winner"] == "model_b":
                    winner_name = row["name_b"]
                elif row["winner"] == "tie":
                    winner_name = "tie"

                results.append(
                    {
                        "id": row["id"],
                        "prompt": row["prompt"],
                        "model_a_name": row["name_a"],
                        "model_b_name": row["name_b"],
                        "winner": row["winner"],
                        "winner_name": winner_name,
                        "created_at": row["created_at"],
                    }
                )
        return results

    # -- Prompt Templates ---------------------------------------------------

    async def create_prompt_template(self, data: PromptTemplateCreate) -> PromptTemplateOut:
        """Create a new prompt template."""
        template_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO prompt_templates (id, name, prompt_text, category, description, usage_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (template_id, data.name, data.prompt_text, data.category, data.description, now),
        )
        await self.db.commit()
        return PromptTemplateOut(
            id=template_id,
            name=data.name,
            prompt_text=data.prompt_text,
            category=data.category,
            description=data.description,
            usage_count=0,
            created_at=now,
        )

    async def get_prompt_template(self, template_id: str) -> PromptTemplateOut | None:
        """Get a prompt template by ID."""
        async with self.db.execute(
            "SELECT * FROM prompt_templates WHERE id = ?", (template_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_template(row)

    async def get_prompt_template_by_name(self, name: str) -> PromptTemplateOut | None:
        """Get a prompt template by name."""
        async with self.db.execute(
            "SELECT * FROM prompt_templates WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return self._row_to_template(row)

    async def list_prompt_templates(
        self, category: str | None = None
    ) -> list[PromptTemplateOut]:
        """List all prompt templates, optionally filtered by category."""
        if category:
            query = "SELECT * FROM prompt_templates WHERE category = ? ORDER BY usage_count DESC, name"
            params = (category,)
        else:
            query = "SELECT * FROM prompt_templates ORDER BY usage_count DESC, name"
            params = ()
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [self._row_to_template(r) for r in rows]

    async def update_prompt_template(
        self, template_id: str, data: PromptTemplateUpdate
    ) -> PromptTemplateOut | None:
        """Update a prompt template's metadata fields."""
        existing = await self.get_prompt_template(template_id)
        if not existing:
            return None

        updates: list[str] = []
        params: list = []
        for field_name in ["name", "prompt_text", "category", "description"]:
            value = getattr(data, field_name, None)
            if value is not None:
                updates.append(f"{field_name} = ?")
                params.append(value)

        if not updates:
            return existing

        params.append(template_id)
        sql = f"UPDATE prompt_templates SET {', '.join(updates)} WHERE id = ?"
        await self.db.execute(sql, params)
        await self.db.commit()
        return await self.get_prompt_template(template_id)

    async def delete_prompt_template(self, template_id: str) -> bool:
        """Delete a prompt template. Returns True if found and deleted."""
        async with self.db.execute(
            "SELECT id FROM prompt_templates WHERE id = ?", (template_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))
        await self.db.commit()
        return True

    async def increment_template_usage(self, template_id: str) -> None:
        """Increment usage counter for a prompt template."""
        await self.db.execute(
            "UPDATE prompt_templates SET usage_count = usage_count + 1 WHERE id = ?",
            (template_id,),
        )
        await self.db.commit()

    async def list_template_categories(self) -> list[str]:
        """List all distinct prompt template categories."""
        async with self.db.execute(
            "SELECT DISTINCT category FROM prompt_templates ORDER BY category"
        ) as cur:
            rows = await cur.fetchall()
            return [r["category"] for r in rows]

    def _row_to_template(self, row: aiosqlite.Row) -> PromptTemplateOut:
        """Convert a database row to a PromptTemplateOut."""
        return PromptTemplateOut(
            id=row["id"],
            name=row["name"],
            prompt_text=row["prompt_text"],
            category=row["category"],
            description=row["description"],
            usage_count=row["usage_count"],
            created_at=row["created_at"],
        )

    # -- Model Trends -------------------------------------------------------

    async def get_model_trends(self, model_id: str, limit: int = 100) -> list:
        """Get rating trend data for chart visualization.

        Returns chronological rating snapshots with opponent info.
        """
        from evalarena.db.models import ModelTrendPoint

        points: list[ModelTrendPoint] = []
        async with self.db.execute(
            "SELECT b.id, b.created_at, b.winner, b.model_a_id, b.model_b_id, "
            "b.model_a_rating_before, b.model_a_rating_after, "
            "b.model_b_rating_before, b.model_b_rating_after, "
            "ma.name as name_a, mb.name as name_b "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "WHERE (b.model_a_id = ? OR b.model_b_id = ?) AND b.winner IS NOT NULL "
            "ORDER BY b.created_at ASC LIMIT ?",
            (model_id, model_id, limit),
        ) as cur:
            async for row in cur:
                is_model_a = row["model_a_id"] == model_id
                opponent = row["name_b"] if is_model_a else row["name_a"]

                if row["winner"] == "tie":
                    result = "tie"
                elif (row["winner"] == "model_a" and is_model_a) or (
                    row["winner"] == "model_b" and not is_model_a
                ):
                    result = "win"
                else:
                    result = "loss"

                if is_model_a:
                    rating = row["model_a_rating_after"] or 1000.0
                    rating_before = row["model_a_rating_before"] or 1000.0
                else:
                    rating = row["model_b_rating_after"] or 1000.0
                    rating_before = row["model_b_rating_before"] or 1000.0

                points.append(
                    ModelTrendPoint(
                        timestamp=row["created_at"],
                        rating=round(rating, 1),
                        battle_id=row["id"],
                        opponent_name=opponent,
                        result=result,
                        rating_change=round(rating - rating_before, 1),
                    )
                )
        return points

    # -- Vote Comments in Battles --------------------------------------------

    async def get_battle_vote_comments(
        self, battle_id: str
    ) -> list[dict[str, str]]:
        """Get all vote comments for a specific battle.

        Args:
            battle_id: The battle to get comments for.

        Returns:
            List of dicts with winner, comment, and created_at.
        """
        results: list[dict[str, str]] = []
        async with self.db.execute(
            "SELECT winner, comment, created_at FROM votes "
            "WHERE battle_id = ? AND comment IS NOT NULL AND comment != '' "
            "ORDER BY created_at ASC",
            (battle_id,),
        ) as cur:
            async for row in cur:
                results.append({
                    "winner": row["winner"],
                    "comment": row["comment"],
                    "created_at": row["created_at"],
                })
        return results

    async def get_battles_with_comments(
        self, limit: int = 30, offset: int = 0
    ) -> list[dict]:
        """Get battles with model names, results, and vote comments.

        Args:
            limit: Max battles to return.
            offset: Pagination offset.

        Returns:
            List of battle dicts with model names, winner, and comments.
        """
        results: list[dict] = []
        async with self.db.execute(
            "SELECT b.*, ma.name as name_a, mb.name as name_b "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "WHERE b.winner IS NOT NULL "
            "ORDER BY b.created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            async for row in cur:
                winner_name = None
                if row["winner"] == "model_a":
                    winner_name = row["name_a"]
                elif row["winner"] == "model_b":
                    winner_name = row["name_b"]
                elif row["winner"] == "tie":
                    winner_name = "tie"

                # Get comments for this battle
                comments = await self.get_battle_vote_comments(row["id"])

                results.append({
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "response_a": row["response_a"],
                    "response_b": row["response_b"],
                    "model_a_name": row["name_a"],
                    "model_b_name": row["name_b"],
                    "winner": row["winner"],
                    "winner_name": winner_name,
                    "comments": comments,
                    "created_at": row["created_at"],
                })
        return results

    # -- Category Stats -----------------------------------------------------

    async def get_category_stats(self) -> list[dict]:
        """Get per-category statistics.

        Returns:
            List of dicts with category, model_count, avg_rating, highest_rating,
            total_battles, and total_votes.
        """
        results: list[dict] = []
        async with self.db.execute(
            "SELECT m.category, "
            "COUNT(DISTINCT m.id) as model_count, "
            "ROUND(AVG(m.rating), 1) as avg_rating, "
            "ROUND(MAX(m.rating), 1) as highest_rating, "
            "COUNT(DISTINCT b.id) as total_battles "
            "FROM models m "
            "LEFT JOIN battles b ON (b.model_a_id = m.id OR b.model_b_id = m.id) "
            "GROUP BY m.category "
            "ORDER BY model_count DESC"
        ) as cur:
            async for row in cur:
                # Count votes for battles in this category
                async with self.db.execute(
                    "SELECT COUNT(v.id) FROM votes v "
                    "JOIN battles b ON v.battle_id = b.id "
                    "JOIN models m ON (b.model_a_id = m.id OR b.model_b_id = m.id) "
                    "WHERE m.category = ?",
                    (row["category"],),
                ) as vote_cur:
                    vote_row = await vote_cur.fetchone()
                    total_votes = vote_row[0] if vote_row else 0

                results.append({
                    "category": row["category"],
                    "model_count": row["model_count"],
                    "avg_rating": row["avg_rating"],
                    "highest_rating": row["highest_rating"],
                    "total_battles": row["total_battles"],
                    "total_votes": total_votes,
                })
        return results

    # -- Comparison Matrix --------------------------------------------------

    async def get_comparison_matrix(self) -> dict:
        """Get a comparison matrix of all model pairs.

        Returns:
            Dict with 'models' (list of model summaries) and 'matrix' (pairwise H2H data).
        """
        models = await self.list_models()
        model_summaries = [
            {
                "id": m.id,
                "name": m.name,
                "category": m.category,
                "rating": m.rating,
                "total_games": m.total_games,
            }
            for m in models
        ]

        matrix: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i, m_a in enumerate(models):
            for j, m_b in enumerate(models):
                if i >= j:
                    continue
                pair_key = tuple(sorted([m_a.id, m_b.id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                async with self.db.execute(
                    "SELECT winner, model_a_id FROM battles "
                    "WHERE ((model_a_id = ? AND model_b_id = ?) "
                    "OR (model_a_id = ? AND model_b_id = ?)) "
                    "AND winner IS NOT NULL",
                    (m_a.id, m_b.id, m_b.id, m_a.id),
                ) as cur:
                    a_wins = 0
                    b_wins = 0
                    ties = 0
                    async for row in cur:
                        if row["winner"] == "tie":
                            ties += 1
                        elif (row["winner"] == "model_a" and row["model_a_id"] == m_a.id) or (
                            row["winner"] == "model_b" and row["model_a_id"] == m_b.id
                        ):
                            a_wins += 1
                        else:
                            b_wins += 1

                    total = a_wins + b_wins + ties
                    if total > 0:
                        matrix.append({
                            "model_a_id": m_a.id,
                            "model_a_name": m_a.name,
                            "model_b_id": m_b.id,
                            "model_b_name": m_b.name,
                            "model_a_wins": a_wins,
                            "model_b_wins": b_wins,
                            "ties": ties,
                            "total": total,
                            "model_a_win_rate": round(a_wins / total * 100, 1),
                        })

        return {"models": model_summaries, "matrix": matrix}

    # -- Seed Templates -----------------------------------------------------

    async def seed_prompt_templates(self, templates: list[dict[str, str]]) -> tuple[int, int]:
        """Bulk-insert seed prompt templates, skipping duplicates by name.

        Args:
            templates: List of dicts with name, prompt_text, category, description.

        Returns:
            Tuple of (added_count, skipped_count).
        """
        added = 0
        skipped = 0
        for t in templates:
            existing = await self.get_prompt_template_by_name(t["name"])
            if existing:
                skipped += 1
                continue
            try:
                await self.create_prompt_template(PromptTemplateCreate(
                    name=t["name"],
                    prompt_text=t["prompt_text"],
                    category=t.get("category", "general"),
                    description=t.get("description", ""),
                ))
                added += 1
            except Exception:
                skipped += 1
        return added, skipped

    async def export_battles(self, limit: int = 1000) -> list[dict]:
        """Export battles with vote details for analysis.

        Returns list of battle dicts with model names, winner, and vote info.
        """
        results: list[dict] = []
        async with self.db.execute(
            "SELECT b.*, ma.name as name_a, mb.name as name_b, "
            "v.winner as vote_winner, v.voter_ip, v.comment as vote_comment, v.created_at as vote_time "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "LEFT JOIN votes v ON b.id = v.battle_id "
            "ORDER BY b.created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            async for row in cur:
                results.append({
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "response_a": row["response_a"],
                    "response_b": row["response_b"],
                    "model_a_name": row["name_a"],
                    "model_b_name": row["name_b"],
                    "winner": row["winner"],
                    "vote_comment": row["vote_comment"] or "",
                    "created_at": row["created_at"],
                })
        return results

    # -- Tournaments --------------------------------------------------------

    async def create_tournament(
        self,
        name: str,
        model_ids: list[str],
        category: str = "general",
        prompts_per_match: int = 1,
        prompt_template_id: str | None = None,
    ) -> dict:
        """Create a round-robin tournament with all model pairs."""
        tournament_id = _uuid()
        now = _now()

        await self.db.execute(
            "INSERT INTO tournaments (id, name, status, category, prompts_per_match, prompt_template_id, created_at) "
            "VALUES (?, ?, 'pending', ?, ?, ?, ?)",
            (tournament_id, name, category, prompts_per_match, prompt_template_id, now),
        )

        for mid in model_ids:
            await self.db.execute(
                "INSERT INTO tournament_models (tournament_id, model_id) VALUES (?, ?)",
                (tournament_id, mid),
            )

        match_ids: list[str] = []
        for i, m_a in enumerate(model_ids):
            for j, m_b in enumerate(model_ids):
                if i >= j:
                    continue
                match_id = _uuid()
                await self.db.execute(
                    "INSERT INTO tournament_matches (id, tournament_id, model_a_id, model_b_id, status, created_at) "
                    "VALUES (?, ?, ?, ?, 'pending', ?)",
                    (match_id, tournament_id, m_a, m_b, now),
                )
                match_ids.append(match_id)

        await self.db.commit()
        return {
            "id": tournament_id, "name": name, "status": "pending",
            "category": category, "prompts_per_match": prompts_per_match,
            "total_matches": len(match_ids), "completed_matches": 0,
            "model_ids": model_ids, "created_at": now,
            "standings": [],
        }

    async def get_tournament(self, tournament_id: str) -> dict | None:
        """Get tournament with standings and match details."""
        async with self.db.execute(
            "SELECT * FROM tournaments WHERE id = ?", (tournament_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None

        model_ids: list[str] = []
        async with self.db.execute(
            "SELECT model_id FROM tournament_models WHERE tournament_id = ?",
            (tournament_id,),
        ) as cur:
            async for r in cur:
                model_ids.append(r["model_id"])

        matches: list[dict] = []
        async with self.db.execute(
            "SELECT tm.*, ma.name as name_a, mb.name as name_b "
            "FROM tournament_matches tm "
            "JOIN models ma ON tm.model_a_id = ma.id "
            "JOIN models mb ON tm.model_b_id = mb.id "
            "WHERE tm.tournament_id = ?",
            (tournament_id,),
        ) as cur:
            async for r in cur:
                battle_ids: list[str] = []
                async with self.db.execute(
                    "SELECT battle_id FROM tournament_match_battles WHERE match_id = ?",
                    (r["id"],),
                ) as bc:
                    async for br in bc:
                        battle_ids.append(br["battle_id"])
                matches.append({
                    "id": r["id"], "tournament_id": tournament_id,
                    "model_a_id": r["model_a_id"], "model_a_name": r["name_a"],
                    "model_b_id": r["model_b_id"], "model_b_name": r["name_b"],
                    "battle_ids": battle_ids, "winner_model_id": r["winner_model_id"],
                    "status": r["status"],
                })

        completed = sum(1 for m in matches if m["status"] == "completed")
        standings: dict[str, dict] = {}
        for mid in model_ids:
            model = await self.get_model(mid)
            standings[mid] = {
                "model_id": mid, "model_name": model.name if model else mid,
                "wins": 0, "losses": 0, "ties": 0, "points": 0.0, "rating_change": 0.0,
            }

        for m in matches:
            if m["status"] != "completed":
                continue
            wid = m["winner_model_id"]
            if wid is None:
                standings[m["model_a_id"]]["ties"] += 1
                standings[m["model_a_id"]]["points"] += 0.5
                standings[m["model_b_id"]]["ties"] += 1
                standings[m["model_b_id"]]["points"] += 0.5
            elif wid == m["model_a_id"]:
                standings[m["model_a_id"]]["wins"] += 1
                standings[m["model_a_id"]]["points"] += 1.0
                standings[m["model_b_id"]]["losses"] += 1
            else:
                standings[m["model_b_id"]]["wins"] += 1
                standings[m["model_b_id"]]["points"] += 1.0
                standings[m["model_a_id"]]["losses"] += 1

        sorted_standings = sorted(standings.values(), key=lambda s: s["points"], reverse=True)
        return {
            "id": row["id"], "name": row["name"], "status": row["status"],
            "category": row["category"], "prompts_per_match": row["prompts_per_match"],
            "total_matches": len(matches), "completed_matches": completed,
            "model_ids": model_ids, "created_at": row["created_at"],
            "standings": sorted_standings, "matches": matches,
        }

    async def list_tournaments(self, status: str | None = None) -> list[dict]:
        """List all tournaments, optionally filtered by status."""
        if status:
            query = "SELECT * FROM tournaments WHERE status = ? ORDER BY created_at DESC"
            params: tuple = (status,)
        else:
            query = "SELECT * FROM tournaments ORDER BY created_at DESC"
            params = ()

        results: list[dict] = []
        async with self.db.execute(query, params) as cur:
            async for row in cur:
                async with self.db.execute(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed "
                    "FROM tournament_matches WHERE tournament_id = ?",
                    (row["id"],),
                ) as mc:
                    mrow = await mc.fetchone()
                    total_matches = mrow["total"] if mrow else 0
                    completed_count = mrow["completed"] if mrow else 0

                model_ids_list: list[str] = []
                async with self.db.execute(
                    "SELECT model_id FROM tournament_models WHERE tournament_id = ?",
                    (row["id"],),
                ) as mc2:
                    async for mr in mc2:
                        model_ids_list.append(mr["model_id"])

                results.append({
                    "id": row["id"], "name": row["name"], "status": row["status"],
                    "category": row["category"], "prompts_per_match": row["prompts_per_match"],
                    "total_matches": total_matches, "completed_matches": completed_count,
                    "model_ids": model_ids_list, "created_at": row["created_at"],
                    "standings": [],
                })
        return results

    async def start_tournament(self, tournament_id: str) -> bool:
        """Mark tournament as in-progress."""
        async with self.db.execute(
            "SELECT id FROM tournaments WHERE id = ? AND status = 'pending'",
            (tournament_id,),
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute(
            "UPDATE tournaments SET status = 'in_progress' WHERE id = ?",
            (tournament_id,),
        )
        await self.db.commit()
        return True

    async def complete_tournament(self, tournament_id: str) -> bool:
        """Mark tournament as completed."""
        async with self.db.execute(
            "SELECT id FROM tournaments WHERE id = ? AND status = 'in_progress'",
            (tournament_id,),
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute(
            "UPDATE tournaments SET status = 'completed' WHERE id = ?",
            (tournament_id,),
        )
        await self.db.commit()
        return True

    async def cancel_tournament(self, tournament_id: str) -> bool:
        """Cancel a tournament."""
        async with self.db.execute(
            "SELECT id FROM tournaments WHERE id = ? AND status IN ('pending', 'in_progress')",
            (tournament_id,),
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute(
            "UPDATE tournaments SET status = 'cancelled' WHERE id = ?",
            (tournament_id,),
        )
        await self.db.commit()
        return True

    async def record_match_battle(
        self, match_id: str, battle_id: str, winner_model_id: str | None
    ) -> bool:
        """Record a battle result for a tournament match."""
        await self.db.execute(
            "INSERT OR IGNORE INTO tournament_match_battles (match_id, battle_id) VALUES (?, ?)",
            (match_id, battle_id),
        )
        await self.db.execute(
            "UPDATE tournament_matches SET winner_model_id = ?, status = 'completed' WHERE id = ?",
            (winner_model_id, match_id),
        )
        await self.db.commit()
        return True

    # -- Full-text Battle Search --------------------------------------------

    async def search_battles(self, query: str, limit: int = 20) -> list[dict]:
        """Search battles by prompt or response content."""
        pattern = f"%{query}%"
        results: list[dict] = []
        seen_ids: set[str] = set()

        async with self.db.execute(
            "SELECT b.*, ma.name as name_a, mb.name as name_b, 1.0 as relevance "
            "FROM battles b "
            "JOIN models ma ON b.model_a_id = ma.id "
            "JOIN models mb ON b.model_b_id = mb.id "
            "WHERE b.prompt LIKE ? "
            "ORDER BY b.created_at DESC LIMIT ?",
            (pattern, limit),
        ) as cur:
            async for row in cur:
                seen_ids.add(row["id"])
                results.append({
                    "id": row["id"], "prompt": row["prompt"],
                    "response_a": row["response_a"], "response_b": row["response_b"],
                    "model_a_name": row["name_a"], "model_b_name": row["name_b"],
                    "winner": row["winner"], "relevance_score": 1.0,
                    "created_at": row["created_at"],
                })

        remaining = limit - len(results)
        if remaining > 0:
            async with self.db.execute(
                "SELECT b.*, ma.name as name_a, mb.name as name_b, 0.5 as relevance "
                "FROM battles b "
                "JOIN models ma ON b.model_a_id = ma.id "
                "JOIN models mb ON b.model_b_id = mb.id "
                "WHERE (b.response_a LIKE ? OR b.response_b LIKE ?) "
                "ORDER BY b.created_at DESC LIMIT ?",
                (pattern, pattern, remaining * 2),
            ) as cur:
                async for row in cur:
                    if row["id"] in seen_ids or len(results) >= limit:
                        continue
                    seen_ids.add(row["id"])
                    results.append({
                        "id": row["id"], "prompt": row["prompt"],
                        "response_a": row["response_a"], "response_b": row["response_b"],
                        "model_a_name": row["name_a"], "model_b_name": row["name_b"],
                        "winner": row["winner"], "relevance_score": 0.5,
                        "created_at": row["created_at"],
                    })

        return results[:limit]

    # -- Win Streak Tracking ------------------------------------------------

    async def get_win_streaks(self) -> list[dict]:
        """Calculate win/loss streaks for all models."""
        models = await self.list_models()
        results: list[dict] = []

        for model in models:
            streaks: list[str] = []
            async with self.db.execute(
                "SELECT b.winner, b.model_a_id, b.model_b_id "
                "FROM battles b "
                "WHERE (b.model_a_id = ? OR b.model_b_id = ?) AND b.winner IS NOT NULL "
                "ORDER BY b.created_at ASC",
                (model.id, model.id),
            ) as cur:
                async for row in cur:
                    is_model_a = row["model_a_id"] == model.id
                    if row["winner"] == "tie":
                        streaks.append("tie")
                    elif (row["winner"] == "model_a" and is_model_a) or (
                        row["winner"] == "model_b" and not is_model_a
                    ):
                        streaks.append("win")
                    else:
                        streaks.append("loss")

            current_streak = 0
            current_type = "none"
            best_win = 0
            best_loss = 0

            if streaks:
                last = streaks[-1]
                current_type = last if last in ("win", "loss") else "none"
                if current_type != "none":
                    current_streak = 0
                    for s in reversed(streaks):
                        if s == current_type:
                            current_streak += 1
                        else:
                            break
                    if current_type == "loss":
                        current_streak = -current_streak

                temp_win = 0
                temp_loss = 0
                for s in streaks:
                    if s == "win":
                        temp_win += 1
                        temp_loss = 0
                        best_win = max(best_win, temp_win)
                    elif s == "loss":
                        temp_loss += 1
                        temp_win = 0
                        best_loss = max(best_loss, temp_loss)
                    else:
                        temp_win = 0
                        temp_loss = 0

            results.append({
                "model_id": model.id, "model_name": model.name,
                "current_streak": current_streak, "current_streak_type": current_type,
                "best_win_streak": best_win, "best_loss_streak": best_loss,
                "total_games": model.total_games,
            })

        results.sort(key=lambda r: r["best_win_streak"], reverse=True)
        return results

    async def get_model_streak(self, model_id: str) -> dict | None:
        """Get win streak info for a single model."""
        streaks = await self.get_win_streaks()
        for s in streaks:
            if s["model_id"] == model_id:
                return s
        return None

    # -- Webhooks -----------------------------------------------------------

    async def create_webhook(
        self, url: str, event: str = "vote", secret: str = ""
    ) -> dict:
        """Register a new webhook."""
        webhook_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO webhooks (id, url, event, secret, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (webhook_id, url, event, secret, now),
        )
        await self.db.commit()
        return {"id": webhook_id, "url": url, "event": event, "active": True, "created_at": now}

    async def list_webhooks(self, event: str | None = None) -> list[dict]:
        """List registered webhooks."""
        if event:
            query = "SELECT * FROM webhooks WHERE event = ? ORDER BY created_at DESC"
            params: tuple = (event,)
        else:
            query = "SELECT * FROM webhooks ORDER BY created_at DESC"
            params = ()
        results: list[dict] = []
        async with self.db.execute(query, params) as cur:
            async for row in cur:
                results.append({
                    "id": row["id"], "url": row["url"], "event": row["event"],
                    "active": bool(row["active"]), "created_at": row["created_at"],
                })
        return results

    async def get_active_webhooks(self, event: str) -> list[dict]:
        """Get all active webhooks for a specific event type."""
        results: list[dict] = []
        async with self.db.execute(
            "SELECT * FROM webhooks WHERE event = ? AND active = 1", (event,)
        ) as cur:
            async for row in cur:
                results.append({
                    "id": row["id"], "url": row["url"], "event": row["event"],
                    "secret": row["secret"], "active": True, "created_at": row["created_at"],
                })
        return results

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        async with self.db.execute(
            "SELECT id FROM webhooks WHERE id = ?", (webhook_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        await self.db.commit()
        return True

    async def deactivate_webhook(self, webhook_id: str) -> bool:
        """Deactivate a webhook."""
        async with self.db.execute(
            "SELECT id FROM webhooks WHERE id = ?", (webhook_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute("UPDATE webhooks SET active = 0 WHERE id = ?", (webhook_id,))
        await self.db.commit()
        return True

    # -- Tags ---------------------------------------------------------------

    async def create_tag(self, name: str, color: str = "#6366f1") -> dict:
        """Create a new tag."""
        tag_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO tags (id, name, color, created_at) VALUES (?, ?, ?, ?)",
            (tag_id, name, color, now),
        )
        await self.db.commit()
        return {"id": tag_id, "name": name, "color": color, "model_count": 0, "created_at": now}

    async def get_tag(self, tag_id: str) -> dict | None:
        """Get a tag by ID."""
        async with self.db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            count = await self._count_tag_models(tag_id)
            return {"id": row["id"], "name": row["name"], "color": row["color"],
                    "model_count": count, "created_at": row["created_at"]}

    async def get_tag_by_name(self, name: str) -> dict | None:
        """Get a tag by name."""
        async with self.db.execute("SELECT * FROM tags WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            count = await self._count_tag_models(row["id"])
            return {"id": row["id"], "name": row["name"], "color": row["color"],
                    "model_count": count, "created_at": row["created_at"]}

    async def list_tags(self) -> list[dict]:
        """List all tags with model counts."""
        results: list[dict] = []
        async with self.db.execute("SELECT * FROM tags ORDER BY name") as cur:
            async for row in cur:
                count = await self._count_tag_models(row["id"])
                results.append({"id": row["id"], "name": row["name"], "color": row["color"],
                                "model_count": count, "created_at": row["created_at"]})
        return results

    async def update_tag(self, tag_id: str, name: str | None = None, color: str | None = None) -> dict | None:
        """Update a tag."""
        existing = await self.get_tag(tag_id)
        if not existing:
            return None
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if color is not None:
            updates.append("color = ?")
            params.append(color)
        if updates:
            params.append(tag_id)
            await self.db.execute(f"UPDATE tags SET {', '.join(updates)} WHERE id = ?", params)
            await self.db.commit()
        return await self.get_tag(tag_id)

    async def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag and all associations."""
        async with self.db.execute("SELECT id FROM tags WHERE id = ?", (tag_id,)) as cur:
            if not await cur.fetchone():
                return False
        await self.db.execute("DELETE FROM model_tags WHERE tag_id = ?", (tag_id,))
        await self.db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await self.db.commit()
        return True

    async def add_model_tag(self, model_id: str, tag_id: str) -> bool:
        """Associate a tag with a model."""
        async with self.db.execute(
            "SELECT 1 FROM models WHERE id = ?", (model_id,)
        ) as cur:
            if not await cur.fetchone():
                raise ValueError(f"Model {model_id} not found")
        async with self.db.execute(
            "SELECT 1 FROM tags WHERE id = ?", (tag_id,)
        ) as cur:
            if not await cur.fetchone():
                raise ValueError(f"Tag {tag_id} not found")
        try:
            await self.db.execute(
                "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            await self.db.commit()
            return True
        except Exception:
            return False  # Already associated

    async def remove_model_tag(self, model_id: str, tag_id: str) -> bool:
        """Remove a tag from a model."""
        await self.db.execute(
            "DELETE FROM model_tags WHERE model_id = ? AND tag_id = ?",
            (model_id, tag_id),
        )
        await self.db.commit()
        return True

    async def get_model_tags(self, model_id: str) -> list[dict]:
        """Get all tags for a model."""
        results: list[dict] = []
        async with self.db.execute(
            "SELECT t.* FROM tags t JOIN model_tags mt ON t.id = mt.tag_id WHERE mt.model_id = ? ORDER BY t.name",
            (model_id,),
        ) as cur:
            async for row in cur:
                results.append({"id": row["id"], "name": row["name"], "color": row["color"]})
        return results

    async def get_models_by_tag(self, tag_id: str) -> list[ModelOut]:
        """Get all models with a specific tag."""
        async with self.db.execute(
            "SELECT m.* FROM models m JOIN model_tags mt ON m.id = mt.model_id WHERE mt.tag_id = ? ORDER BY m.rating DESC",
            (tag_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    async def _count_tag_models(self, tag_id: str) -> int:
        """Count models with a specific tag."""
        async with self.db.execute(
            "SELECT COUNT(*) FROM model_tags WHERE tag_id = ?", (tag_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    # -- Rating Decay -------------------------------------------------------

    async def apply_rating_decay(
        self,
        inactive_days: int = 30,
        decay_rate: float = 0.02,
        min_rating: float = 100.0,
    ) -> dict:
        """Apply rating decay to inactive models.

        Models that haven't had a battle in ``inactive_days`` days lose
        ``decay_rate`` of their rating above ``min_rating`` per inactive period.

        Returns:
            Dict with models_affected, total_rating_decayed, and details list.
        """
        from datetime import timedelta
        from evalarena.db.models import DecayDetail

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=inactive_days)).isoformat()

        # Find models with no battles since cutoff
        inactive_models: list[tuple[str, str, float]] = []
        async with self.db.execute(
            "SELECT m.id, m.name, m.rating FROM models m WHERE m.id NOT IN ("
            "  SELECT DISTINCT model_a_id FROM battles WHERE created_at > ? "
            "  UNION "
            "  SELECT DISTINCT model_b_id FROM battles WHERE created_at > ?"
            ")",
            (cutoff, cutoff),
        ) as cur:
            async for row in cur:
                inactive_models.append((row["id"], row["name"], row["rating"]))

        details: list[DecayDetail] = []
        total_decayed = 0.0

        for model_id, model_name, old_rating in inactive_models:
            if old_rating <= min_rating:
                continue

            # Calculate how many inactive periods
            async with self.db.execute(
                "SELECT MAX(created_at) FROM battles WHERE model_a_id = ? OR model_b_id = ?",
                (model_id, model_id),
            ) as cur:
                row = await cur.fetchone()
                last_battle = row[0]

            if last_battle:
                last_dt = datetime.fromisoformat(last_battle.replace("Z", "+00:00"))
                inactive_period_count = max(1, int((now - last_dt).total_seconds() / (86400 * inactive_days)))
            else:
                # Never had a battle - check creation date
                async with self.db.execute(
                    "SELECT created_at FROM models WHERE id = ?", (model_id,)
                ) as cur:
                    crow = await cur.fetchone()
                    if crow:
                        created = datetime.fromisoformat(crow[0].replace("Z", "+00:00"))
                        inactive_period_count = max(1, int((now - created).total_seconds() / (86400 * inactive_days)))
                    else:
                        inactive_period_count = 1

            decay_amount = (old_rating - min_rating) * decay_rate * inactive_period_count
            new_rating = max(min_rating, old_rating - decay_amount)
            new_rating = round(new_rating, 1)
            decay_amount = round(old_rating - new_rating, 1)

            if decay_amount > 0:
                await self.db.execute(
                    "UPDATE models SET rating = ? WHERE id = ?", (new_rating, model_id)
                )
                total_decayed += decay_amount
                details.append(DecayDetail(
                    model_id=model_id, model_name=model_name,
                    old_rating=round(old_rating, 1), new_rating=new_rating,
                    decay_amount=decay_amount, inactive_days=inactive_period_count * inactive_days,
                ))

        await self.db.commit()
        return {
            "models_affected": len(details),
            "total_rating_decayed": round(total_decayed, 1),
            "details": details,
        }

    # -- Dashboard Analytics ------------------------------------------------

    async def get_rating_distribution(self) -> dict:
        """Get rating distribution histogram."""
        from evalarena.db.models import RatingDistributionBucket

        models = await self.list_models()
        if not models:
            return {
                "buckets": [], "total_models": 0,
                "mean_rating": 0.0, "median_rating": 0.0,
            }

        ratings = [m.rating for m in models]
        mean_rating = round(sum(ratings) / len(ratings), 1)
        sorted_ratings = sorted(ratings)
        mid = len(sorted_ratings) // 2
        median_rating = round(
            sorted_ratings[mid] if len(sorted_ratings) % 2 == 1
            else (sorted_ratings[mid - 1] + sorted_ratings[mid]) / 2, 1
        )

        # Create 100-point buckets from 0 to max
        max_r = int(max(ratings)) + 100
        bucket_size = 100
        buckets: list[RatingDistributionBucket] = []
        for start in range(0, max_r, bucket_size):
            end = start + bucket_size
            count = sum(1 for r in ratings if start <= r < end)
            buckets.append(RatingDistributionBucket(
                range_start=start, range_end=end, count=count,
            ))

        return {
            "buckets": [b.model_dump() for b in buckets],
            "total_models": len(models),
            "mean_rating": mean_rating,
            "median_rating": median_rating,
        }

    async def get_activity_trends(self, days: int = 14) -> list[dict]:
        """Get daily battle and vote counts over the last N days."""
        from datetime import timedelta

        results: list[dict] = []
        now = datetime.now(timezone.utc)

        for i in range(days - 1, -1, -1):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            async with self.db.execute(
                "SELECT COUNT(*) FROM battles WHERE created_at LIKE ?",
                (f"{day}%",),
            ) as cur:
                row = await cur.fetchone()
                battle_count = row[0] if row else 0

            async with self.db.execute(
                "SELECT COUNT(*) FROM votes WHERE created_at LIKE ?",
                (f"{day}%",),
            ) as cur:
                row = await cur.fetchone()
                vote_count = row[0] if row else 0

            results.append({"date": day, "battles": battle_count, "votes": vote_count})
        return results

    async def get_top_movers(self, days: int = 7, limit: int = 5) -> tuple[list[dict], list[dict]]:
        """Get top gainers and losers over the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Find rating changes for models that had battles in the period
        changes: list[dict] = []
        async with self.db.execute(
            "SELECT DISTINCT m.id, m.name, m.rating FROM models m "
            "JOIN battles b ON (b.model_a_id = m.id OR b.model_b_id = m.id) "
            "WHERE b.created_at > ? AND b.winner IS NOT NULL",
            (cutoff,),
        ) as cur:
            async for row in cur:
                model_id = row["id"]
                current_rating = row["rating"]

                # Get oldest rating in the period
                async with self.db.execute(
                    "SELECT model_a_rating_before, model_b_rating_before, model_a_id "
                    "FROM battles WHERE (model_a_id = ? OR model_b_id = ?) "
                    "AND created_at > ? AND winner IS NOT NULL "
                    "ORDER BY created_at ASC LIMIT 1",
                    (model_id, model_id, cutoff),
                ) as bc:
                    brow = await bc.fetchone()
                    if brow:
                        if brow["model_a_id"] == model_id:
                            old_rating = brow["model_a_rating_before"] or 1000.0
                        else:
                            old_rating = brow["model_b_rating_before"] or 1000.0
                    else:
                        old_rating = 1000.0

                change = round(current_rating - old_rating, 1)
                changes.append({
                    "model_id": model_id, "model_name": row["name"],
                    "rating_change": change, "current_rating": round(current_rating, 1),
                    "period_days": days,
                })

        gainers = sorted(changes, key=lambda x: x["rating_change"], reverse=True)[:limit]
        losers = sorted(changes, key=lambda x: x["rating_change"])[:limit]

        return gainers, losers

    # -- Audit Log --------------------------------------------------------

    async def log_audit_action(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        details: str = "",
        actor_ip: str | None = None,
    ) -> dict:
        """Record an audit log entry.

        Args:
            action: Action performed (e.g. 'model.create', 'vote.submit').
            entity_type: Type of entity affected (model, battle, vote, tag).
            entity_id: ID of the affected entity.
            details: JSON string with additional context.
            actor_ip: IP address of the actor.

        Returns:
            The created audit log entry as a dict.
        """
        entry_id = _uuid()
        now = _now()
        await self.db.execute(
            "INSERT INTO audit_log (id, action, entity_type, entity_id, details, actor_ip, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, action, entity_type, entity_id, details, actor_ip or "", now),
        )
        await self.db.commit()
        return {
            "id": entry_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
            "actor_ip": actor_ip or "",
            "created_at": now,
        }

    async def list_audit_logs(
        self,
        action: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List audit log entries with optional filters.

        Args:
            action: Filter by action type.
            entity_type: Filter by entity type.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of audit log entry dicts.
        """
        conditions: list[str] = []
        params: list = []

        if action:
            conditions.append("action = ?")
            params.append(action)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM audit_log{where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # -- Full Backup / Restore --------------------------------------------

    async def create_backup(self) -> dict:
        """Create a complete backup of all data.

        Returns a JSON-serializable dict containing all models, battles, votes,
        tags, prompt templates, and API keys.
        """
        import json as json_mod

        # Models
        async with self.db.execute("SELECT * FROM models") as cur:
            models = [dict(r) for r in await cur.fetchall()]

        # Battles
        async with self.db.execute("SELECT * FROM battles") as cur:
            battles = [dict(r) for r in await cur.fetchall()]

        # Votes
        async with self.db.execute("SELECT * FROM votes") as cur:
            votes = [dict(r) for r in await cur.fetchall()]

        # Tags
        async with self.db.execute("SELECT * FROM tags") as cur:
            tags = [dict(r) for r in await cur.fetchall()]

        # Model-Tag associations
        async with self.db.execute("SELECT * FROM model_tags") as cur:
            model_tags = [dict(r) for r in await cur.fetchall()]

        # Prompt templates
        async with self.db.execute("SELECT * FROM prompt_templates") as cur:
            templates = [dict(r) for r in await cur.fetchall()]

        # API keys (exported without secrets for security)
        async with self.db.execute("SELECT key, name, active, created_at FROM api_keys") as cur:
            api_keys = [dict(r) for r in await cur.fetchall()]

        # Tournaments
        async with self.db.execute("SELECT * FROM tournaments") as cur:
            tournaments = [dict(r) for r in await cur.fetchall()]
        async with self.db.execute("SELECT * FROM tournament_models") as cur:
            tournament_models = [dict(r) for r in await cur.fetchall()]
        async with self.db.execute("SELECT * FROM tournament_matches") as cur:
            tournament_matches = [dict(r) for r in await cur.fetchall()]

        # Webhooks
        async with self.db.execute("SELECT * FROM webhooks") as cur:
            webhooks_list = [dict(r) for r in await cur.fetchall()]

        return {
            "version": "0.9.0",
            "exported_at": _now(),
            "models": models,
            "battles": battles,
            "votes": votes,
            "tags": tags,
            "model_tags": model_tags,
            "prompt_templates": templates,
            "api_keys": api_keys,
            "tournaments": tournaments,
            "tournament_models": tournament_models,
            "tournament_matches": tournament_matches,
            "webhooks": webhooks_list,
        }

    async def restore_from_backup(self, backup: dict) -> dict:
        """Restore data from a backup dict.

        Handles idempotent restore: existing records are skipped by primary key.

        Args:
            backup: The backup dict (from create_backup).

        Returns:
            Summary dict with counts of restored items and any errors.
        """
        errors: list[str] = []
        restored: dict[str, int] = {}

        # Version check
        version = backup.get("version", "unknown")
        if not version.startswith("0."):
            errors.append(f"Unknown backup version: {version}")

        # Restore models
        count = 0
        for model in backup.get("models", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO models "
                    "(id, name, category, description, organization, parameter_count, "
                    "provider, api_model_id, rating, wins, losses, ties, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        model["id"], model["name"], model.get("category", "general"),
                        model.get("description", ""), model.get("organization", ""),
                        model.get("parameter_count", ""), model.get("provider", ""),
                        model.get("api_model_id", ""), model["rating"],
                        model["wins"], model["losses"], model["ties"], model["created_at"],
                    ),
                )
                count += 1
            except Exception as e:
                errors.append(f"Model {model.get('name', '?')}: {e}")
        restored["models_restored"] = count

        # Restore battles
        count = 0
        for battle in backup.get("battles", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO battles "
                    "(id, model_a_id, model_b_id, prompt, response_a, response_b, winner, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        battle["id"], battle["model_a_id"], battle["model_b_id"],
                        battle["prompt"], battle["response_a"], battle["response_b"],
                        battle.get("winner"), battle["created_at"],
                    ),
                )
                count += 1
            except Exception as e:
                errors.append(f"Battle {battle.get('id', '?')}: {e}")
        restored["battles_restored"] = count

        # Restore votes
        count = 0
        for vote in backup.get("votes", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO votes (id, battle_id, winner, voter_ip, comment, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        vote["id"], vote["battle_id"], vote["winner"],
                        vote.get("voter_ip", ""), vote.get("comment", ""),
                        vote["created_at"],
                    ),
                )
                count += 1
            except Exception as e:
                errors.append(f"Vote {vote.get('id', '?')}: {e}")
        restored["votes_restored"] = count

        # Restore tags
        count = 0
        for tag in backup.get("tags", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO tags (id, name, color, created_at) VALUES (?, ?, ?, ?)",
                    (tag["id"], tag["name"], tag.get("color", "#6366f1"), tag["created_at"]),
                )
                count += 1
            except Exception as e:
                errors.append(f"Tag {tag.get('name', '?')}: {e}")
        restored["tags_restored"] = count

        # Restore model_tags
        count = 0
        for mt in backup.get("model_tags", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                    (mt["model_id"], mt["tag_id"]),
                )
                count += 1
            except Exception as e:
                errors.append(f"model_tag: {e}")
        restored["model_tags_restored"] = count

        # Restore prompt templates
        count = 0
        for tmpl in backup.get("prompt_templates", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO prompt_templates "
                    "(id, name, prompt_text, category, description, usage_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        tmpl["id"], tmpl["name"], tmpl["prompt_text"],
                        tmpl.get("category", "general"), tmpl.get("description", ""),
                        tmpl.get("usage_count", 0), tmpl["created_at"],
                    ),
                )
                count += 1
            except Exception as e:
                errors.append(f"Template {tmpl.get('name', '?')}: {e}")
        restored["templates_restored"] = count

        # Restore webhooks
        count = 0
        for wh in backup.get("webhooks", []):
            try:
                await self.db.execute(
                    "INSERT OR IGNORE INTO webhooks (id, url, event, secret, active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (wh["id"], wh["url"], wh.get("event", "vote"),
                     wh.get("secret", ""), wh.get("active", 1), wh["created_at"]),
                )
                count += 1
            except Exception as e:
                errors.append(f"Webhook: {e}")
        restored["webhooks_restored"] = count

        await self.db.commit()
        restored["errors"] = errors
        return restored

    # -- Multi-dimension Scoring -------------------------------------------

    async def create_vote(
        self,
        data,
        voter_ip: str | None = None,
        dimensions: dict[str, int] | None = None,
    ) -> bool:
        """Submit a vote and update ELO ratings.

        Args:
            data: VoteCreate with battle_id, winner, and optional comment.
            voter_ip: IP address for deduplication.
            dimensions: Optional scoring dimensions (e.g. fluency, accuracy, creativity).

        Returns:
            True if the vote was recorded.
        """
        from evalarena.db.models import Winner

        battle = await self.get_battle(data.battle_id)
        if not battle:
            raise ValueError(f"Battle {data.battle_id} not found")
        if battle["winner"] is not None:
            return False

        if voter_ip:
            async with self.db.execute(
                "SELECT id FROM votes WHERE battle_id = ? AND voter_ip = ?",
                (data.battle_id, voter_ip),
            ) as cur:
                if await cur.fetchone():
                    raise ValueError("You have already voted on this battle")

        vote_id = _uuid()
        now = _now()
        comment = getattr(data, "comment", "") or ""

        await self.db.execute(
            "INSERT INTO votes (id, battle_id, winner, voter_ip, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (vote_id, data.battle_id, data.winner.value, voter_ip, comment, now),
        )

        # Save dimensions if provided
        if dimensions:
            for dim_name, dim_value in dimensions.items():
                await self.db.execute(
                    "INSERT INTO vote_dimensions (vote_id, dimension_name, score) "
                    "VALUES (?, ?, ?)",
                    (vote_id, dim_name, dim_value),
                )

        await self.set_battle_winner(data.battle_id, data.winner.value)

        # Update ELO ratings
        model_a = await self._get_rating(battle["model_a_id"])
        model_b = await self._get_rating(battle["model_b_id"])
        a_before = model_a.rating
        b_before = model_b.rating

        if data.winner == Winner.TIE:
            update_ratings(model_a, model_b, data.battle_id, is_tie=True)
        elif data.winner == Winner.MODEL_A:
            update_ratings(model_a, model_b, data.battle_id)
        else:
            update_ratings(model_b, model_a, data.battle_id)

        await self.db.execute(
            "UPDATE battles SET model_a_rating_before = ?, model_b_rating_before = ?, "
            "model_a_rating_after = ?, model_b_rating_after = ? WHERE id = ?",
            (a_before, b_before, model_a.rating, model_b.rating, data.battle_id),
        )
        await self._update_model_rating(battle["model_a_id"], model_a)
        await self._update_model_rating(battle["model_b_id"], model_b)

        # Log audit action
        await self.log_audit_action(
            action="vote.create",
            entity_type="battle",
            entity_id=data.battle_id,
            details=json.dumps({
                "winner": data.winner.value,
                "comment": comment,
                "dimensions": dimensions or {},
                "model_a_before": a_before,
                "model_a_after": model_a.rating,
                "model_b_before": b_before,
                "model_b_after": model_b.rating,
            }),
            actor_ip=voter_ip,
        )

        await self.db.commit()
        return True

    async def get_battle_dimensions(self, battle_id: str) -> dict[str, int]:
        """Get scoring dimensions for a battle's vote.

        Args:
            battle_id: The battle ID.

        Returns:
            Dict mapping dimension name to score.
        """
        # Get vote for this battle
        async with self.db.execute(
            "SELECT id FROM votes WHERE battle_id = ?", (battle_id,)
        ) as cur:
            vote_row = await cur.fetchone()
            if not vote_row:
                return {}

        async with self.db.execute(
            "SELECT dimension_name, score FROM vote_dimensions WHERE vote_id = ?",
            (vote_row["id"],),
        ) as cur:
            rows = await cur.fetchall()
            return {r["dimension_name"]: r["score"] for r in rows}

    # -- Comparison Report -------------------------------------------------

    async def generate_comparison_report(self, model_id: str) -> dict:
        """Generate a detailed comparison report for a model.

        Includes win/loss record against each opponent, rating history,
        and statistical summary.

        Args:
            model_id: The model to generate the report for.

        Returns:
            Comprehensive report dict.
        """
        model = await self.get_model(model_id)
        if not model:
            return {"model_id": model_id, "error": "Model not found"}

        # Get all battles involving this model
        async with self.db.execute(
            "SELECT * FROM battles WHERE (model_a_id = ? OR model_b_id = ?) AND winner IS NOT NULL "
            "ORDER BY created_at ASC",
            (model_id, model_id),
        ) as cur:
            battles = await cur.fetchall()

        # Build opponent statistics
        opponent_stats: dict[str, dict] = {}
        rating_history: list[dict] = []

        for battle in battles:
            is_a = battle["model_a_id"] == model_id
            opponent_id = battle["model_b_id"] if is_a else battle["model_a_id"]

            # Get opponent name
            opp = await self.get_model(opponent_id)
            opp_name = opp.name if opp else opponent_id

            if opponent_id not in opponent_stats:
                opponent_stats[opponent_id] = {
                    "model_id": opponent_id,
                    "model_name": opp_name,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                }

            stats = opponent_stats[opponent_id]
            if battle["winner"] == "tie":
                stats["ties"] += 1
                result = "tie"
            elif (is_a and battle["winner"] == "model_a") or (not is_a and battle["winner"] == "model_b"):
                stats["wins"] += 1
                result = "win"
            else:
                stats["losses"] += 1
                result = "loss"

            # Rating history
            rating_before = battle["model_a_rating_before"] if is_a else battle["model_b_rating_before"]
            rating_after = battle["model_a_rating_after"] if is_a else battle["model_b_rating_after"]
            if rating_before and rating_after:
                rating_history.append({
                    "battle_id": battle["id"],
                    "rating_before": round(rating_before, 1),
                    "rating_after": round(rating_after, 1),
                    "rating_change": round(rating_after - rating_before, 1),
                    "opponent_name": opp_name,
                    "result": result,
                    "created_at": battle["created_at"],
                })

        # Calculate per-opponent win rates
        opponents = list(opponent_stats.values())
        for opp in opponents:
            total = opp["wins"] + opp["losses"] + opp["ties"]
            opp["total"] = total
            opp["win_rate"] = round(opp["wins"] / total * 100, 1) if total > 0 else 0.0

        return {
            "model_id": model_id,
            "model_name": model.name,
            "current_rating": round(model.rating, 1),
            "total_battles": len(battles),
            "overall_win_rate": model.win_rate,
            "opponents": opponents,
            "rating_history": rating_history,
            "best_rating": max((h["rating_after"] for h in rating_history), default=model.rating),
            "worst_rating": min((h["rating_after"] for h in rating_history), default=model.rating),
        }
