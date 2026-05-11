"""Model registration and management."""
from dataclasses import dataclass, field
from datetime import datetime

from evalarena.db.database import get_db


@dataclass
class ModelInfo:
    """Represents a registered model."""
    id: int
    name: str
    organization: str | None = None
    description: str | None = None
    elo_rating: float = 1000.0
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    created_at: str = ""
    updated_at: str = ""

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.games_played == 0:
            return 0.0
        return round(self.wins / self.games_played * 100, 1)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "organization": self.organization,
            "description": self.description,
            "elo_rating": self.elo_rating,
            "games_played": self.games_played,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "win_rate": self.win_rate,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


async def register_model(
    name: str,
    organization: str | None = None,
    description: str | None = None,
    initial_elo: float = 1000.0,
) -> ModelInfo:
    """Register a new model in the arena."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO models (name, organization, description, elo_rating)
           VALUES (?, ?, ?, ?)""",
        (name, organization, description, initial_elo),
    )
    await db.commit()
    return await get_model(cursor.lastrowid)


async def get_model(model_id: int) -> ModelInfo | None:
    """Get a model by ID."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_model(row)


async def get_model_by_name(name: str) -> ModelInfo | None:
    """Get a model by name."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM models WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_model(row)


async def list_models(order_by: str = "elo_rating", descending: bool = True) -> list[ModelInfo]:
    """List all registered models."""
    allowed = {"elo_rating", "games_played", "wins", "name", "created_at"}
    if order_by not in allowed:
        order_by = "elo_rating"
    direction = "DESC" if descending else "ASC"
    db = await get_db()
    cursor = await db.execute(
        f"SELECT * FROM models ORDER BY {order_by} {direction}"
    )
    rows = await cursor.fetchall()
    return [_row_to_model(row) for row in rows]


async def update_model_rating(
    model_id: int,
    new_elo: float,
    won: bool = False,
    lost: bool = False,
    tied: bool = False,
) -> None:
    """Update model's ELO rating and game stats."""
    db = await get_db()
    await db.execute(
        """UPDATE models SET
            elo_rating = ?,
            games_played = games_played + 1,
            wins = wins + ?,
            losses = losses + ?,
            ties = ties + ?,
            updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_elo, int(won), int(lost), int(tied), model_id),
    )
    await db.commit()


async def delete_model(model_id: int) -> bool:
    """Delete a model. Returns True if deleted."""
    db = await get_db()
    cursor = await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
    await db.commit()
    return cursor.rowcount > 0


def _row_to_model(row) -> ModelInfo:
    return ModelInfo(
        id=row["id"],
        name=row["name"],
        organization=row["organization"],
        description=row["description"],
        elo_rating=row["elo_rating"],
        games_played=row["games_played"],
        wins=row["wins"],
        losses=row["losses"],
        ties=row["ties"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
