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

    from ..db import SessionLocal, init_db
    from ..services.registry import registry

    init_db()
    console = Console()
    console.print(f"[bold blue]Nimbus Engine[/] v{settings.app_version}")
    console.print(f"Database: {settings.effective_database_url}")
    console.print(f"Environment: {settings.environment}")

    # Register adapters
    try:
        from ..providers.oci.adapter import OCIProviderAdapter
        registry.register_adapter("oci", OCIProviderAdapter)
    except ImportError:
        pass

    console.print(f"Supported providers: {', '.join(registry.supported_types) or 'none'}")

    db = SessionLocal()
    try:
        providers = registry.list_providers(db, active_only=False)
        if providers:
            table = Table(title="Registered Providers")
            table.add_column("ID", style="cyan")
            table.add_column("Type")
            table.add_column("Name")
            table.add_column("Region")
            table.add_column("Active", style="green")
            for p in providers:
                table.add_row(p.id, p.provider_type, p.display_name, p.region, "✔" if p.is_active else "✖")
            console.print(table)
        else:
            console.print("[dim]No providers registered. Use 'nimbus providers add' to register one.[/dim]")
    finally:
        db.close()


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


# ---------------------------------------------------------------------------
# Provider commands
# ---------------------------------------------------------------------------


@cli.group()
def providers():
    """Manage cloud providers."""
    pass


@providers.command("list")
def providers_list():
    """List registered providers."""
    from rich.console import Console
    from rich.table import Table

    from ..db import SessionLocal, init_db
    from ..services.registry import registry

    init_db()
    console = Console()
    db = SessionLocal()
    try:
        items = registry.list_providers(db, active_only=False)
        if not items:
            console.print("[dim]No providers registered.[/dim]")
            return
        table = Table(title="Providers")
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Region")
        table.add_column("Active")
        for p in items:
            table.add_row(p.id, p.provider_type, p.display_name, p.region, "✔" if p.is_active else "✖")
        console.print(table)
    finally:
        db.close()


@providers.command("add")
@click.option("--id", "provider_id", required=True, help="Unique provider ID")
@click.option("--type", "provider_type", required=True, help="Provider type (oci, azure, cloudflare, proxmox)")
@click.option("--name", "display_name", required=True, help="Display name")
@click.option("--region", default="", help="Cloud region")
@click.option("--credentials", "credentials_path", default="", help="Path to credentials file")
def providers_add(provider_id: str, provider_type: str, display_name: str, region: str, credentials_path: str):
    """Register a new provider."""
    from ..db import SessionLocal, init_db
    from ..services.registry import registry

    init_db()
    db = SessionLocal()
    try:
        provider = registry.create_provider(
            db,
            id=provider_id,
            provider_type=provider_type,
            display_name=display_name,
            region=region,
            credentials_path=credentials_path,
        )
        click.echo(f"✔ Provider '{provider.id}' registered ({provider.provider_type})")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Resource commands
# ---------------------------------------------------------------------------


@cli.group()
def resources():
    """Manage cloud resources."""
    pass


@resources.command("list")
@click.option("--provider", "provider_id", default=None, help="Filter by provider ID")
@click.option("--type", "resource_type", default=None, help="Filter by resource type")
def resources_list(provider_id: str | None, resource_type: str | None):
    """List tracked resources."""
    from rich.console import Console
    from rich.table import Table

    from ..db import SessionLocal, init_db
    from ..models.resource import CloudResource

    init_db()
    console = Console()
    db = SessionLocal()
    try:
        q = db.query(CloudResource)
        if provider_id:
            q = q.filter(CloudResource.provider_id == provider_id)
        if resource_type:
            q = q.filter(CloudResource.resource_type == resource_type)
        items = q.order_by(CloudResource.display_name).all()
        if not items:
            console.print("[dim]No resources tracked.[/dim]")
            return
        table = Table(title="Resources")
        table.add_column("ID", style="cyan", max_width=12)
        table.add_column("Provider")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Protection")
        for r in items:
            status_style = "green" if r.status == "running" else "yellow" if r.status == "stopped" else "red"
            table.add_row(
                r.id[:12], r.provider_id, r.resource_type,
                r.display_name, f"[{status_style}]{r.status}[/{status_style}]",
                r.protection_level,
            )
        console.print(table)
    finally:
        db.close()


@resources.command("sync")
@click.argument("provider_id")
def resources_sync(provider_id: str):
    """Sync resources from a cloud provider."""
    from rich.console import Console

    from ..db import SessionLocal, init_db
    from ..models.resource import CloudResource
    from ..providers.oci.adapter import OCIProviderAdapter
    from ..services.registry import registry

    registry.register_adapter("oci", OCIProviderAdapter)

    console = Console()
    init_db()
    db = SessionLocal()
    try:
        provider = registry.get_provider(db, provider_id)
        if provider is None:
            console.print(f"[red]Provider '{provider_id}' not found[/red]")
            return

        adapter = registry.get_adapter(provider_id, db)
        remote = adapter.list_resources()
        console.print(f"Found {len(remote)} resources from {provider_id}")

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        created = updated = 0
        for r in remote:
            existing = (
                db.query(CloudResource)
                .filter(CloudResource.provider_id == provider_id, CloudResource.external_id == r["external_id"])
                .first()
            )
            if existing:
                existing.status = r.get("status", existing.status)
                existing.last_seen_at = now
                updated += 1
            else:
                db.add(CloudResource(
                    provider_id=provider_id,
                    resource_type=r.get("resource_type", "unknown"),
                    external_id=r["external_id"],
                    display_name=r.get("display_name", ""),
                    status=r.get("status", "unknown"),
                    last_seen_at=now,
                ))
                created += 1
        db.commit()
        console.print(f"[green]✔ Synced: {created} created, {updated} updated[/green]")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
