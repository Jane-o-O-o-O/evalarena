"""SQLite database connection and operations.

Uses a simple in-process SQLite database with aiosqlite for async access.
All state lives in a single file; schema is auto-created on first use.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from evalarena.core.elo import ModelRating, update_ratings, rating_confidence_interval
from evalarena.db.models import (
    BattleCreate,
    BattleOut,
    BattleSummary,
    HeadToHead,
    LeaderboardEntry,
    ModelCreate,
    ModelDetail,
    ModelOut,
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

    async def create_vote(self, data: VoteCreate, voter_ip: str | None = None) -> bool:
        """Submit a vote and update ELO ratings.

        Returns True if the vote was recorded. Returns False if battle already voted on.
        Raises ValueError if battle not found or IP already voted.
        """
        # Check battle exists and hasn't been voted on
        battle = await self.get_battle(data.battle_id)
        if not battle:
            raise ValueError(f"Battle {data.battle_id} not found")
        if battle["winner"] is not None:
            return False

        # Prevent duplicate voting from same IP on same battle
        if voter_ip:
            async with self.db.execute(
                "SELECT id FROM votes WHERE battle_id = ? AND voter_ip = ?",
                (data.battle_id, voter_ip),
            ) as cur:
                if await cur.fetchone():
                    raise ValueError("You have already voted on this battle")

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

        # Snapshot ratings before update
        a_before = model_a.rating
        b_before = model_b.rating

        if data.winner == Winner.TIE:
            update_ratings(model_a, model_b, data.battle_id, is_tie=True)
        elif data.winner == Winner.MODEL_A:
            update_ratings(model_a, model_b, data.battle_id)
        else:
            update_ratings(model_b, model_a, data.battle_id)

        # Store rating changes in battle record
        await self.db.execute(
            "UPDATE battles SET model_a_rating_before = ?, model_b_rating_before = ?, "
            "model_a_rating_after = ?, model_b_rating_after = ? WHERE id = ?",
            (a_before, b_before, model_a.rating, model_b.rating, data.battle_id),
        )

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
