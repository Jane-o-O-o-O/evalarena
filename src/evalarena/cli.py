"""CLI entry point for EvalArena."""

import click


@click.group()
@click.version_option(package_name="evalarena")
def main():
    """EvalArena - LLM Evaluation Arena."""
    pass


@main.command()
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=8080, type=int, help="Server port")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--api-key", default=None, help="API key for write operations (optional)")
def serve(host: str, port: int, db_path: str, api_key: str | None):
    """Start the evaluation arena server."""
    import uvicorn
    from evalarena.app import create_app

    app = create_app(db_path=db_path, api_key=api_key)
    click.echo(f"Starting EvalArena on {host}:{port}")
    if api_key:
        click.echo("API key authentication enabled for write operations")
    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command("init-db")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def init_db(db_path: str):
    """Initialize the database."""
    import asyncio
    from evalarena.db.database import Database

    async def _init():
        db = Database(db_path)
        await db.connect()
        await db.close()
        click.echo(f"Database initialized: {db_path}")

    asyncio.run(_init())


@main.command()
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "csv"]))
@click.option("--output", "output_path", default="leaderboard.csv")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--category", default=None, help="Filter by category")
def export(fmt: str, output_path: str, db_path: str, category: str | None):
    """Export leaderboard data."""
    import asyncio
    import json
    import csv
    from evalarena.db.database import Database

    async def _export():
        db = Database(db_path)
        await db.connect()
        entries = await db.get_leaderboard(category=category)
        await db.close()

        if fmt == "json":
            data = [e.model_dump() for e in entries]
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
        else:
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "rank", "model_id", "name", "category", "rating", "wins", "losses", "ties", "total_games", "win_rate"
                ])
                writer.writeheader()
                for e in entries:
                    writer.writerow(e.model_dump())

        click.echo(f"Exported {len(entries)} entries -> {output_path}")

    asyncio.run(_export())


@main.command()
@click.argument("name")
@click.option("--category", default="general", help="Model category (e.g., coding, writing, reasoning)")
@click.option("--description", default="", help="Model description")
@click.option("--organization", default="", help="Organization or author")
@click.option("--params", "parameter_count", default="", help="Parameter count (e.g. 7B, 70B)")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def add_model(name: str, category: str, description: str, organization: str, parameter_count: str, db_path: str):
    """Register a new model."""
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import ModelCreate

    async def _add():
        db = Database(db_path)
        await db.connect()
        try:
            model = await db.create_model(ModelCreate(
                name=name, category=category, description=description,
                organization=organization, parameter_count=parameter_count,
            ))
            click.echo(f"Added model: {model.name} (id={model.id}, category={model.category})")
            if model.organization:
                click.echo(f"  Organization: {model.organization}")
            if model.parameter_count:
                click.echo(f"  Parameters: {model.parameter_count}")
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
        finally:
            await db.close()

    asyncio.run(_add())


@main.command("list-models")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--category", default=None, help="Filter by category")
def list_models_cmd(db_path: str, category: str | None):
    """List all registered models."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        models = await db.list_models(category=category)
        await db.close()

        if not models:
            click.echo("No models registered.")
            return

        click.echo(f"{'Name':<25} {'Category':<15} {'Rating':>8} {'W':>5} {'L':>5} {'T':>5} {'Win%':>6}")
        click.echo("-" * 75)
        for m in models:
            click.echo(f"{m.name:<25} {m.category:<15} {m.rating:>8.1f} {m.wins:>5} {m.losses:>5} {m.ties:>5} {m.win_rate:>5.1f}%")

    asyncio.run(_list())


@main.command()
@click.argument("model_a")
@click.argument("model_b")
@click.option("--prompt", required=True, help="The prompt for the battle")
@click.option("--response-a", required=True, help="Response from model A")
@click.option("--response-b", required=True, help="Response from model B")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def battle(model_a: str, model_b: str, prompt: str, response_a: str, response_b: str, db_path: str):
    """Create a battle between two models by name."""
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import BattleCreate

    async def _battle():
        db = Database(db_path)
        await db.connect()
        try:
            ma = await db.get_model_by_name(model_a)
            mb = await db.get_model_by_name(model_b)
            if not ma:
                click.echo(f"Model '{model_a}' not found", err=True)
                return
            if not mb:
                click.echo(f"Model '{model_b}' not found", err=True)
                return

            b = await db.create_battle(BattleCreate(
                prompt=prompt,
                response_a=response_a,
                response_b=response_b,
                model_a_id=ma.id,
                model_b_id=mb.id,
            ))
            click.echo(f"Battle created: {b.id}")
        finally:
            await db.close()

    asyncio.run(_battle())


@main.command()
@click.argument("battle_id")
@click.argument("winner", type=click.Choice(["model_a", "model_b", "tie"]))
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def vote(battle_id: str, winner: str, db_path: str):
    """Vote on a battle outcome.

    WINNER must be one of: model_a, model_b, tie.
    """
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import VoteCreate, Winner

    async def _vote():
        db = Database(db_path)
        await db.connect()
        try:
            winner_enum = Winner(winner)
            data = VoteCreate(battle_id=battle_id, winner=winner_enum)
            recorded = await db.create_vote(data)
            if recorded:
                click.echo(f"Vote recorded: {winner} wins battle {battle_id}")
            else:
                click.echo("Battle already voted on", err=True)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
        finally:
            await db.close()

    asyncio.run(_vote())


@main.command("battles")
@click.option("--limit", default=20, type=int, help="Number of battles to show")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--unvoted", is_flag=True, help="Show only unvoted battles")
def list_battles_cmd(limit: int, db_path: str, unvoted: bool):
    """List recent battles."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        battles = await db.list_battles(limit=limit, unvoted_only=unvoted)
        await db.close()

        if not battles:
            click.echo("No battles found.")
            return

        click.echo(f"{'ID':<15} {'Prompt':<40} {'Voted':>6} {'Created':<25}")
        click.echo("-" * 90)
        for b in battles:
            prompt_short = b.prompt[:37] + "..." if len(b.prompt) > 37 else b.prompt
            voted = "✓" if b.voted else "✗"
            click.echo(f"{b.id:<15} {prompt_short:<40} {voted:>6} {b.created_at[:19]}")

    asyncio.run(_list())


@main.command("import-models")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--category", default="general", help="Default category for imported models")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def import_models(file_path: str, category: str, db_path: str):
    """Bulk import models from a JSON or CSV file.

    JSON format: [{"name": "model-1", "category": "coding"}, ...]
    CSV format: name,category (category column optional)
    """
    import asyncio
    import json
    import csv
    from pathlib import Path
    from evalarena.db.database import Database
    from evalarena.db.models import ModelCreate

    async def _import():
        db = Database(db_path)
        await db.connect()

        path = Path(file_path)
        models_data: list[dict] = []

        if path.suffix == ".json":
            with open(path) as f:
                raw = json.load(f)
            for item in raw:
                if isinstance(item, str):
                    models_data.append({"name": item, "category": category})
                elif isinstance(item, dict):
                    models_data.append({
                        "name": item["name"],
                        "category": item.get("category", category),
                    })
        elif path.suffix == ".csv":
            with open(path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    models_data.append({
                        "name": row["name"],
                        "category": row.get("category", category),
                    })
        else:
            click.echo(f"Unsupported file format: {path.suffix}. Use .json or .csv", err=True)
            await db.close()
            return

        added = 0
        skipped = 0
        for item in models_data:
            try:
                await db.create_model(ModelCreate(name=item["name"], category=item["category"]))
                click.echo(f"  + {item['name']} ({item['category']})")
                added += 1
            except Exception as e:
                click.echo(f"  ~ {item['name']}: {e}")
                skipped += 1

        await db.close()
        click.echo(f"\nImport complete: {added} added, {skipped} skipped")

    asyncio.run(_import())


@main.command("create-key")
@click.argument("name")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def create_key(name: str, db_path: str):
    """Create a new API key."""
    import asyncio
    import secrets
    from evalarena.db.database import Database

    async def _create():
        db = Database(db_path)
        await db.connect()
        key = "evl_" + secrets.token_urlsafe(32)
        await db.create_api_key(key, name)
        await db.close()
        click.echo(f"API key created: {key}")
        click.echo(f"Name: {name}")
        click.echo("Store this key securely — it cannot be retrieved again.")

    asyncio.run(_create())


@main.command("list-keys")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def list_keys_cmd(db_path: str):
    """List all API keys (values masked)."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        keys = await db.list_api_keys()
        await db.close()

        if not keys:
            click.echo("No API keys registered.")
            return

        click.echo(f"{'Key Prefix':<18} {'Name':<25} {'Active':>7} {'Created':<25}")
        click.echo("-" * 80)
        for k in keys:
            active = "✓" if k["active"] else "✗"
            click.echo(f"{k['key_prefix']:<18} {k['name']:<25} {active:>7} {k['created_at'][:19]}")

    asyncio.run(_list())


@main.command()
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def stats(db_path: str):
    """Show platform statistics."""
    import asyncio
    from evalarena.db.database import Database

    async def _stats():
        db = Database(db_path)
        await db.connect()
        s = await db.get_stats()
        await db.close()

        click.echo("EvalArena Platform Statistics")
        click.echo("=" * 40)
        click.echo(f"  Models:          {s.total_models}")
        click.echo(f"  Battles:         {s.total_battles}")
        click.echo(f"  Votes:           {s.total_votes}")
        click.echo(f"  Avg Rating:      {s.avg_rating}")
        click.echo(f"  Highest Rating:  {s.highest_rating}")
        click.echo(f"  Lowest Rating:   {s.lowest_rating}")
        click.echo(f"  Most Active:     {s.most_active_model or 'N/A'}")
        click.echo(f"  Battles Today:   {s.battles_today}")

    asyncio.run(_stats())


@main.command("head-to-head")
@click.argument("model_a")
@click.argument("model_b")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def head_to_head_cmd(model_a: str, model_b: str, db_path: str):
    """Compare two models head-to-head by name."""
    import asyncio
    from evalarena.db.database import Database

    async def _h2h():
        db = Database(db_path)
        await db.connect()
        try:
            ma = await db.get_model_by_name(model_a)
            mb = await db.get_model_by_name(model_b)
            if not ma:
                click.echo(f"Model '{model_a}' not found", err=True)
                return
            if not mb:
                click.echo(f"Model '{model_b}' not found", err=True)
                return

            h = await db.head_to_head(ma.id, mb.id)

            click.echo(f"{h.model_a} vs {h.model_b}")
            click.echo("=" * 40)
            click.echo(f"  {h.model_a} wins:   {h.model_a_wins}")
            click.echo(f"  {h.model_b} wins:   {h.model_b_wins}")
            click.echo(f"  Ties:         {h.ties}")
            click.echo(f"  Total:        {h.total_battles}")
            if h.total_battles > 0:
                click.echo(f"  {h.model_a} win%: {h.model_a_win_rate}%")
        finally:
            await db.close()

    asyncio.run(_h2h())


@main.command("delete-model")
@click.argument("name")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def delete_model_cmd(name: str, db_path: str, yes: bool):
    """Delete a model by name."""
    import asyncio
    from evalarena.db.database import Database

    async def _delete():
        db = Database(db_path)
        await db.connect()
        try:
            model = await db.get_model_by_name(name)
            if not model:
                click.echo(f"Model '{name}' not found", err=True)
                return
            if not yes:
                click.confirm(
                    f"Delete model '{model.name}' (rating={model.rating:.0f}, "
                    f"games={model.total_games})? This cannot be undone.",
                    abort=True,
                )
            deleted = await db.delete_model(model.id)
            if deleted:
                click.echo(f"Deleted model: {model.name}")
            else:
                click.echo("Failed to delete model", err=True)
        finally:
            await db.close()

    asyncio.run(_delete())


@main.command("search-models")
@click.argument("query")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--limit", default=20, type=int, help="Max results")
def search_models_cmd(query: str, db_path: str, limit: int):
    """Search models by name or organization."""
    import asyncio
    from evalarena.db.database import Database

    async def _search():
        db = Database(db_path)
        await db.connect()
        models = await db.search_models(query, limit=limit)
        await db.close()

        if not models:
            click.echo(f"No models matching '{query}'.")
            return

        click.echo(f"Found {len(models)} model(s) matching '{query}':")
        click.echo(f"{'Name':<25} {'Org':<20} {'Category':<15} {'Rating':>8} {'Games':>6}")
        click.echo("-" * 80)
        for m in models:
            org = (m.organization[:17] + "...") if len(m.organization) > 17 else m.organization
            click.echo(
                f"{m.name:<25} {org:<20} {m.category:<15} {m.rating:>8.1f} {m.total_games:>6}"
            )

    asyncio.run(_search())


@main.command("reset-db")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def reset_db_cmd(db_path: str, yes: bool):
    """Delete all data and reinitialize the database."""
    import asyncio
    import os
    from evalarena.db.database import Database

    async def _reset():
        if not yes:
            click.confirm(
                f"This will permanently delete all data in '{db_path}'. Continue?",
                abort=True,
            )
        if os.path.exists(db_path):
            os.remove(db_path)
        db = Database(db_path)
        await db.connect()
        await db.close()
        click.echo(f"Database reset: {db_path}")

    asyncio.run(_reset())


if __name__ == "__main__":
    main()
