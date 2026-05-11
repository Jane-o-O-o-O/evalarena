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
def serve(host: str, port: int, db_path: str):
    """Start the evaluation arena server."""
    import uvicorn
    from evalarena.app import create_app

    app = create_app(db_path=db_path)
    click.echo(f"Starting EvalArena on {host}:{port}")
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
def export(fmt: str, output_path: str, db_path: str):
    """Export leaderboard data."""
    import asyncio
    import json
    import csv
    from evalarena.db.database import Database

    async def _export():
        db = Database(db_path)
        await db.connect()
        entries = await db.get_leaderboard()
        await db.close()

        if fmt == "json":
            data = [e.model_dump() for e in entries]
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
        else:
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "rank", "model_id", "name", "rating", "wins", "losses", "ties", "total_games", "win_rate"
                ])
                writer.writeheader()
                for e in entries:
                    writer.writerow(e.model_dump())

        click.echo(f"Exported {len(entries)} entries -> {output_path}")

    asyncio.run(_export())


@main.command()
@click.argument("name")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def add_model(name: str, db_path: str):
    """Register a new model."""
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import ModelCreate

    async def _add():
        db = Database(db_path)
        await db.connect()
        try:
            model = await db.create_model(ModelCreate(name=name))
            click.echo(f"Added model: {model.name} (id={model.id})")
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
        finally:
            await db.close()

    asyncio.run(_add())


@main.command("list-models")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def list_models_cmd(db_path: str):
    """List all registered models."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        models = await db.list_models()
        await db.close()

        if not models:
            click.echo("No models registered.")
            return

        click.echo(f"{'Name':<25} {'Rating':>8} {'W':>5} {'L':>5} {'T':>5} {'Win%':>6}")
        click.echo("-" * 60)
        for m in models:
            click.echo(f"{m.name:<25} {m.rating:>8.1f} {m.wins:>5} {m.losses:>5} {m.ties:>5} {m.win_rate:>5.1f}%")

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


if __name__ == "__main__":
    main()
