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


@main.command("update-model")
@click.argument("name")
@click.option("--new-name", default=None, help="New name for the model")
@click.option("--category", default=None, help="New category")
@click.option("--description", default=None, help="New description")
@click.option("--organization", default=None, help="New organization")
@click.option("--params", "parameter_count", default=None, help="New parameter count")
@click.option("--provider", default=None, help="LLM provider name (e.g. openai, anthropic)")
@click.option("--api-model-id", default=None, help="Model ID for the LLM provider API")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def update_model_cmd(
    name: str,
    new_name: str | None,
    category: str | None,
    description: str | None,
    organization: str | None,
    parameter_count: str | None,
    provider: str | None,
    api_model_id: str | None,
    db_path: str,
):
    """Update a model's metadata by name."""
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import ModelUpdate

    async def _update():
        db = Database(db_path)
        await db.connect()
        try:
            model = await db.get_model_by_name(name)
            if not model:
                click.echo(f"Model '{name}' not found", err=True)
                return

            update_data = ModelUpdate(
                name=new_name,
                category=category,
                description=description,
                organization=organization,
                parameter_count=parameter_count,
                provider=provider,
                api_model_id=api_model_id,
            )
            updated = await db.update_model(model.id, update_data)
            if updated:
                click.echo(f"Updated model: {updated.name}")
                if new_name:
                    click.echo(f"  Name: {name} -> {new_name}")
                if category:
                    click.echo(f"  Category: {updated.category}")
                if provider:
                    click.echo(f"  Provider: {updated.provider}")
                if api_model_id:
                    click.echo(f"  API Model ID: {updated.api_model_id}")
            else:
                click.echo("Failed to update model", err=True)
        finally:
            await db.close()

    asyncio.run(_update())


@main.command("providers")
def providers_cmd():
    """List available LLM providers and their configuration status."""
    from evalarena.providers import list_providers
    from evalarena.providers.mock_provider import MockProvider
    from evalarena.providers.openai_provider import OpenAIProvider
    from evalarena.providers.anthropic_provider import AnthropicProvider
    from evalarena.providers import register_provider

    register_provider(MockProvider())
    register_provider(OpenAIProvider())
    register_provider(AnthropicProvider())

    providers = list_providers()
    if not providers:
        click.echo("No providers registered.")
        return

    click.echo(f"{'Provider':<15} {'Configured':>12}")
    click.echo("-" * 30)
    for p in providers:
        status = "✓ Ready" if p["configured"] else "✗ No API key"
        click.echo(f"{p['name']:<15} {status:>12}")


# -- Prompt Template Commands -----------------------------------------------


@main.command("add-template")
@click.argument("name")
@click.option("--prompt", "prompt_text", required=True, help="The prompt text")
@click.option("--category", default="general", help="Template category")
@click.option("--description", default="", help="Brief description")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def add_template(name: str, prompt_text: str, category: str, description: str, db_path: str):
    """Create a new prompt template."""
    import asyncio
    from evalarena.db.database import Database
    from evalarena.db.models import PromptTemplateCreate

    async def _add():
        db = Database(db_path)
        await db.connect()
        try:
            template = await db.create_prompt_template(PromptTemplateCreate(
                name=name, prompt_text=prompt_text,
                category=category, description=description,
            ))
            click.echo(f"Added template: {template.name} (id={template.id}, category={template.category})")
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
        finally:
            await db.close()

    asyncio.run(_add())


@main.command("list-templates")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--category", default=None, help="Filter by category")
def list_templates_cmd(db_path: str, category: str | None):
    """List all prompt templates."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        templates = await db.list_prompt_templates(category=category)
        await db.close()

        if not templates:
            click.echo("No prompt templates found.")
            return

        click.echo(f"{'Name':<30} {'Category':<15} {'Uses':>5} {'Prompt Preview':<40}")
        click.echo("-" * 95)
        for t in templates:
            preview = t.prompt_text[:37] + "..." if len(t.prompt_text) > 37 else t.prompt_text
            click.echo(f"{t.name:<30} {t.category:<15} {t.usage_count:>5} {preview:<40}")

    asyncio.run(_list())


@main.command("delete-template")
@click.argument("name")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def delete_template_cmd(name: str, db_path: str, yes: bool):
    """Delete a prompt template by name."""
    import asyncio
    from evalarena.db.database import Database

    async def _delete():
        db = Database(db_path)
        await db.connect()
        try:
            template = await db.get_prompt_template_by_name(name)
            if not template:
                click.echo(f"Template '{name}' not found", err=True)
                return
            if not yes:
                click.confirm(f"Delete template '{template.name}'?", abort=True)
            deleted = await db.delete_prompt_template(template.id)
            if deleted:
                click.echo(f"Deleted template: {template.name}")
        finally:
            await db.close()

    asyncio.run(_delete())


@main.command("export-battles")
@click.option("--output", "output_path", default="battles_export.json", help="Output file path")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "csv"]))
@click.option("--limit", default=1000, type=int, help="Max battles to export")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def export_battles(output_path: str, fmt: str, limit: int, db_path: str):
    """Export battle data with votes and comments."""
    import asyncio
    import json
    import csv
    from evalarena.db.database import Database

    async def _export():
        db = Database(db_path)
        await db.connect()
        battles = await db.export_battles(limit=limit)
        await db.close()

        if fmt == "json":
            with open(output_path, "w") as f:
                json.dump(battles, f, indent=2, ensure_ascii=False)
        else:
            if battles:
                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=battles[0].keys())
                    writer.writeheader()
                    for b in battles:
                        writer.writerow(b)

        click.echo(f"Exported {len(battles)} battles -> {output_path}")

    asyncio.run(_export())


@main.command("random-battle")
@click.option("--template", "template_name", default=None, help="Use a prompt template by name")
@click.option("--prompt", default=None, help="Custom prompt (if no template)")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def random_battle_cmd(template_name: str | None, prompt: str | None, db_path: str):
    """Create a random battle between two models with a prompt."""
    import asyncio
    import random
    from evalarena.db.database import Database
    from evalarena.db.models import BattleCreate

    async def _random():
        if not template_name and not prompt:
            click.echo("Provide --template or --prompt", err=True)
            return

        db = Database(db_path)
        await db.connect()
        try:
            actual_prompt = prompt
            if template_name:
                template = await db.get_prompt_template_by_name(template_name)
                if not template:
                    click.echo(f"Template '{template_name}' not found", err=True)
                    return
                actual_prompt = template.prompt_text
                await db.increment_template_usage(template.id)

            models = await db.list_models()
            if len(models) < 2:
                click.echo("Need at least 2 models registered", err=True)
                return

            pair = random.sample(models, 2)
            click.echo(f"Random pair: {pair[0].name} vs {pair[1].name}")
            click.echo(f"Prompt: {actual_prompt[:80]}...")
            click.echo()
            click.echo("Provide responses (or use 'evalarena serve' + auto-battle API):")
            click.echo(f"  Model A ({pair[0].name}): enter response text")
            click.echo(f"  Model B ({pair[1].name}): enter response text")
            click.echo()
            click.echo("For auto-battle, use:")
            click.echo(f'  curl -X POST http://localhost:8080/api/arena/auto-battle \\')
            click.echo(f'    -H "Content-Type: application/json" \\')
            click.echo(f'    -d \'{{"prompt": "{actual_prompt[:50]}...", "model_a_id": "{pair[0].id}", "model_b_id": "{pair[1].id}"}}\'')
        finally:
            await db.close()

    asyncio.run(_random())


@main.command("seed-templates")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--category", default=None, help="Only seed templates for this category")
def seed_templates_cmd(db_path: str, category: str | None):
    """Load built-in prompt templates into the database.

    Seeds templates for coding, writing, reasoning, math, and general categories.
    Existing templates (by name) are skipped.
    """
    import asyncio
    from evalarena.db.database import Database
    from evalarena.seed_templates import get_seed_templates, get_seed_templates_by_category

    async def _seed():
        db = Database(db_path)
        await db.connect()
        if category:
            templates = get_seed_templates_by_category(category)
        else:
            templates = get_seed_templates()

        if not templates:
            click.echo(f"No templates found{f' for category: {category}' if category else ''}.")
            await db.close()
            return

        added, skipped = await db.seed_prompt_templates(templates)
        await db.close()
        click.echo(f"Seed templates loaded: {added} added, {skipped} skipped")
        if category:
            click.echo(f"  Category filter: {category}")

    asyncio.run(_seed())


@main.command("comparison-matrix")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def comparison_matrix_cmd(db_path: str):
    """Show pairwise model comparison matrix."""
    import asyncio
    from evalarena.db.database import Database

    async def _matrix():
        db = Database(db_path)
        await db.connect()
        data = await db.get_comparison_matrix()
        await db.close()

        models = data["models"]
        matrix = data["matrix"]

        if not models:
            click.echo("No models registered.")
            return

        click.echo(f"Models: {len(models)}")
        click.echo(f"Comparison pairs: {len(matrix)}")
        click.echo()

        if not matrix:
            click.echo("No battles between models yet.")
            return

        click.echo(f"{'Matchup':<45} {'W':>5} {'L':>5} {'T':>5} {'Win%':>7}")
        click.echo("-" * 70)
        for entry in sorted(matrix, key=lambda x: x["total"], reverse=True):
            matchup = f"{entry['model_a_name']} vs {entry['model_b_name']}"
            click.echo(
                f"{matchup:<45} {entry['model_a_wins']:>5} {entry['model_b_wins']:>5} "
                f"{entry['ties']:>5} {entry['model_a_win_rate']:>6.1f}%"
            )

    asyncio.run(_matrix())


@main.command("category-stats")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def category_stats_cmd(db_path: str):
    """Show per-category statistics."""
    import asyncio
    from evalarena.db.database import Database

    async def _stats():
        db = Database(db_path)
        await db.connect()
        stats = await db.get_category_stats()
        await db.close()

        if not stats:
            click.echo("No categories found.")
            return

        click.echo(f"{'Category':<15} {'Models':>7} {'Avg Rating':>11} {'Highest':>9} {'Battles':>9} {'Votes':>7}")
        click.echo("-" * 65)
        for s in stats:
            click.echo(
                f"{s['category']:<15} {s['model_count']:>7} {s['avg_rating']:>11.1f} "
                f"{s['highest_rating']:>9.1f} {s['total_battles']:>9} {s['total_votes']:>7}"
            )

    asyncio.run(_stats())


# -- Tournament Commands --------------------------------------------------


@main.command("create-tournament")
@click.argument("name")
@click.option("--models", required=True, help="Comma-separated model names or IDs")
@click.option("--category", default="general", help="Tournament category")
@click.option("--prompts-per-match", default=1, type=int, help="Battles per pair")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def create_tournament_cmd(name: str, models: str, category: str, prompts_per_match: int, db_path: str):
    """Create a round-robin tournament."""
    import asyncio
    from evalarena.db.database import Database

    async def _create():
        db = Database(db_path)
        await db.connect()
        try:
            model_names = [m.strip() for m in models.split(",")]
            model_ids: list[str] = []
            for mn in model_names:
                m = await db.get_model_by_name(mn)
                if not m:
                    click.echo(f"Model '{mn}' not found", err=True)
                    return
                model_ids.append(m.id)

            if len(model_ids) < 2:
                click.echo("Need at least 2 models", err=True)
                return

            result = await db.create_tournament(
                name=name, model_ids=model_ids,
                category=category, prompts_per_match=prompts_per_match,
            )
            click.echo(f"Tournament created: {result['name']} (id={result['id']})")
            click.echo(f"  Models: {len(model_ids)}")
            click.echo(f"  Matches: {result['total_matches']}")
            click.echo(f"  Prompts per match: {prompts_per_match}")
        finally:
            await db.close()

    asyncio.run(_create())


@main.command("list-tournaments")
@click.option("--status", default=None, help="Filter by status")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def list_tournaments_cmd(status: str | None, db_path: str):
    """List all tournaments."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        tournaments = await db.list_tournaments(status=status)
        await db.close()

        if not tournaments:
            click.echo("No tournaments found.")
            return

        click.echo(f"{'Name':<30} {'Status':<12} {'Models':>7} {'Matches':>9} {'Done':>6}")
        click.echo("-" * 70)
        for t in tournaments:
            click.echo(
                f"{t['name']:<30} {t['status']:<12} {len(t['model_ids']):>7} "
                f"{t['total_matches']:>9} {t['completed_matches']:>6}"
            )

    asyncio.run(_list())


@main.command("tournament-standings")
@click.argument("tournament_id")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def tournament_standings_cmd(tournament_id: str, db_path: str):
    """Show tournament standings."""
    import asyncio
    from evalarena.db.database import Database

    async def _standings():
        db = Database(db_path)
        await db.connect()
        t = await db.get_tournament(tournament_id)
        await db.close()

        if not t:
            click.echo(f"Tournament '{tournament_id}' not found", err=True)
            return

        click.echo(f"Tournament: {t['name']} ({t['status']})")
        click.echo(f"Progress: {t['completed_matches']}/{t['total_matches']} matches")
        click.echo()

        if not t['standings']:
            click.echo("No standings yet.")
            return

        click.echo(f"{'#':<4} {'Model':<25} {'W':>5} {'L':>5} {'T':>5} {'Pts':>6}")
        click.echo("-" * 55)
        for i, s in enumerate(t['standings'], 1):
            click.echo(
                f"{i:<4} {s['model_name']:<25} {s['wins']:>5} {s['losses']:>5} "
                f"{s['ties']:>5} {s['points']:>6.1f}"
            )

    asyncio.run(_standings())


# -- Search Commands ------------------------------------------------------


@main.command("search-battles")
@click.argument("query")
@click.option("--limit", default=20, type=int, help="Max results")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def search_battles_cmd(query: str, limit: int, db_path: str):
    """Search battles by prompt or response content."""
    import asyncio
    from evalarena.db.database import Database

    async def _search():
        db = Database(db_path)
        await db.connect()
        results = await db.search_battles(query, limit=limit)
        await db.close()

        if not results:
            click.echo(f"No battles matching '{query}'.")
            return

        click.echo(f"Found {len(results)} battle(s) matching '{query}':")
        click.echo(f"{'ID':<15} {'Model A':<15} {'Model B':<15} {'Prompt':<40}")
        click.echo("-" * 90)
        for r in results:
            prompt_short = r['prompt'][:37] + "..." if len(r['prompt']) > 37 else r['prompt']
            click.echo(f"{r['id']:<15} {r['model_a_name']:<15} {r['model_b_name']:<15} {prompt_short:<40}")

    asyncio.run(_search())


# -- Streak Commands ------------------------------------------------------


@main.command("win-streaks")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def win_streaks_cmd(db_path: str):
    """Show win streak leaderboard."""
    import asyncio
    from evalarena.db.database import Database

    async def _streaks():
        db = Database(db_path)
        await db.connect()
        streaks = await db.get_win_streaks()
        await db.close()

        if not streaks:
            click.echo("No models with battle history.")
            return

        click.echo(f"{'Model':<25} {'Current':>9} {'Best Win':>10} {'Best Loss':>11} {'Games':>7}")
        click.echo("-" * 70)
        for s in streaks:
            current = s['current_streak']
            current_str = f"+{current}" if current > 0 else str(current)
            if s['current_streak_type'] == 'none':
                current_str = "—"
            click.echo(
                f"{s['model_name']:<25} {current_str:>9} {s['best_win_streak']:>10} "
                f"{s['best_loss_streak']:>11} {s['total_games']:>7}"
            )

    asyncio.run(_streaks())


# -- Webhook Commands -----------------------------------------------------


@main.command("create-webhook")
@click.argument("url")
@click.option("--event", default="vote", help="Event type (vote/battle/tournament)")
@click.option("--secret", default="", help="HMAC secret for signature verification")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def create_webhook_cmd(url: str, event: str, secret: str, db_path: str):
    """Register a webhook for event notifications."""
    import asyncio
    from evalarena.db.database import Database

    async def _create():
        db = Database(db_path)
        await db.connect()
        result = await db.create_webhook(url=url, event=event, secret=secret)
        await db.close()
        click.echo(f"Webhook created: {result['id']}")
        click.echo(f"  URL: {url}")
        click.echo(f"  Event: {event}")

    asyncio.run(_create())


@main.command("list-webhooks")
@click.option("--event", default=None, help="Filter by event type")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def list_webhooks_cmd(event: str | None, db_path: str):
    """List registered webhooks."""
    import asyncio
    from evalarena.db.database import Database

    async def _list():
        db = Database(db_path)
        await db.connect()
        webhooks = await db.list_webhooks(event=event)
        await db.close()

        if not webhooks:
            click.echo("No webhooks registered.")
            return

        click.echo(f"{'ID':<15} {'URL':<40} {'Event':<10} {'Active':>7}")
        click.echo("-" * 75)
        for w in webhooks:
            active = "✓" if w['active'] else "✗"
            click.echo(f"{w['id']:<15} {w['url']:<40} {w['event']:<10} {active:>7}")

    asyncio.run(_list())


# -- Backup/Restore Commands ----------------------------------------------


@main.command("backup")
@click.option("--output", "output_path", default="evalarena_backup.json", help="Backup file path")
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
def backup_cmd(output_path: str, db_path: str):
    """Full database backup to JSON."""
    import asyncio
    import json
    from evalarena.db.database import Database

    async def _backup():
        db = Database(db_path)
        await db.connect()

        backup_data: dict = {
            "version": "0.7.0",
            "models": [],
            "battles": [],
            "prompt_templates": [],
            "webhooks": [],
        }

        # Export models
        models = await db.list_models()
        for m in models:
            backup_data["models"].append(m.model_dump())

        # Export battles
        battles = await db.export_battles(limit=100000)
        backup_data["battles"] = battles

        # Export templates
        templates = await db.list_prompt_templates()
        backup_data["prompt_templates"] = [t.model_dump() for t in templates]

        # Export webhooks
        webhooks = await db.list_webhooks()
        backup_data["webhooks"] = webhooks

        await db.close()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        click.echo(f"Backup saved: {output_path}")
        click.echo(f"  Models: {len(backup_data['models'])}")
        click.echo(f"  Battles: {len(backup_data['battles'])}")
        click.echo(f"  Templates: {len(backup_data['prompt_templates'])}")
        click.echo(f"  Webhooks: {len(backup_data['webhooks'])}")

    asyncio.run(_backup())


@main.command("restore")
@click.argument("backup_path", type=click.Path(exists=True))
@click.option("--db", "db_path", default="evalarena.db", help="Database file path")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def restore_cmd(backup_path: str, db_path: str, yes: bool):
    """Restore database from a JSON backup."""
    import asyncio
    import json
    from evalarena.db.database import Database
    from evalarena.db.models import ModelCreate, PromptTemplateCreate

    async def _restore():
        with open(backup_path, encoding="utf-8") as f:
            data = json.load(f)

        model_count = len(data.get("models", []))
        battle_count = len(data.get("battles", []))

        if not yes:
            click.confirm(
                f"Restore {model_count} models and {battle_count} battles to '{db_path}'? "
                f"This will add to existing data.",
                abort=True,
            )

        db = Database(db_path)
        await db.connect()

        # Restore models (skip duplicates by name)
        restored_models = 0
        for m in data.get("models", []):
            existing = await db.get_model_by_name(m["name"])
            if not existing:
                try:
                    await db.create_model(ModelCreate(
                        name=m["name"],
                        category=m.get("category", "general"),
                        description=m.get("description", ""),
                        organization=m.get("organization", ""),
                        parameter_count=m.get("parameter_count", ""),
                    ))
                    restored_models += 1
                except Exception:
                    pass

        # Restore templates
        restored_templates = 0
        for t in data.get("prompt_templates", []):
            existing = await db.get_prompt_template_by_name(t["name"])
            if not existing:
                try:
                    await db.create_prompt_template(PromptTemplateCreate(
                        name=t["name"],
                        prompt_text=t["prompt_text"],
                        category=t.get("category", "general"),
                        description=t.get("description", ""),
                    ))
                    restored_templates += 1
                except Exception:
                    pass

        await db.close()

        click.echo(f"Restore complete:")
        click.echo(f"  Models restored: {restored_models}")
        click.echo(f"  Templates restored: {restored_templates}")
        click.echo(f"  (Battles require re-creation through the arena API)")

    asyncio.run(_restore())


if __name__ == "__main__":
    main()
