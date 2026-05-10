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
def serve(host, port):
    """Start the evaluation arena server."""
    click.echo(f"Starting EvalArena on {host}:{port}")


@main.command("init-db")
def init_db():
    """Initialize the database."""
    click.echo("Initializing database...")


@main.command()
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "csv"]))
@click.option("--output", "output_path", default="leaderboard.csv")
def export(fmt, output_path):
    """Export leaderboard data."""
    click.echo(f"Exporting leaderboard as {fmt} -> {output_path}")


if __name__ == "__main__":
    main()
