# Nimbus CLI — main entry point
"""nimbus CLI — manage multi-cloud infrastructure from the terminal."""

from __future__ import annotations

import click

from ..config import settings


@click.group()
@click.version_option(version=settings.app_version, prog_name="nimbus")
def cli():
    """Nimbus — Personal multi-cloud orchestration platform."""
    pass


@cli.command()
def status():
    """Show Nimbus engine status and registered providers."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"[bold blue]Nimbus Engine[/] v{settings.app_version}")
    console.print(f"Database: {settings.effective_database_url}")
    console.print(f"Environment: {settings.environment}")


@cli.command()
def serve():
    """Start the Nimbus API server."""
    import uvicorn
    uvicorn.run(
        "nimbus.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    cli()
