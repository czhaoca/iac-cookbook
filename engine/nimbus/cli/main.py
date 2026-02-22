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
    from ..app import _register_adapters
    _register_adapters()

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


# ---------------------------------------------------------------------------
# Budget commands
# ---------------------------------------------------------------------------


@cli.group()
def budget():
    """Manage budget rules and spending."""
    pass


@budget.command("status")
@click.option("--provider", "provider_id", default=None, help="Filter by provider ID")
def budget_status(provider_id: str | None):
    """Show current budget status."""
    from rich.console import Console
    from rich.table import Table

    from ..db import SessionLocal, init_db
    from ..services.budget_monitor import check_budget

    init_db()
    console = Console()
    db = SessionLocal()
    try:
        statuses = check_budget(db, provider_id)
        if not statuses:
            console.print("[dim]No budget rules configured.[/dim]")
            return
        table = Table(title="Budget Status")
        table.add_column("Provider")
        table.add_column("Period")
        table.add_column("Spent", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Usage", justify="right")
        table.add_column("Status")
        table.add_column("Action")
        for s in statuses:
            color = {"ok": "green", "warning": "yellow", "exceeded": "red"}.get(s.status, "white")
            table.add_row(
                s.provider_id or "Global", s.period,
                f"${s.total_spent:.2f}", f"${s.monthly_limit:.2f}",
                f"{s.utilization:.0%}",
                f"[{color}]{s.status}[/{color}]",
                s.action_on_exceed,
            )
        console.print(table)
    finally:
        db.close()


@budget.command("add")
@click.option("--provider", "provider_id", default=None, help="Provider ID (omit for global)")
@click.option("--limit", "monthly_limit", required=True, type=float, help="Monthly spend limit (USD)")
@click.option("--threshold", "alert_threshold", default=0.8, type=float, help="Alert threshold (0.0-1.0)")
@click.option("--action", "action_on_exceed", default="alert",
              type=click.Choice(["alert", "scale_down", "terminate_ephemeral", "firewall_lockdown"]),
              help="Action when budget exceeded")
def budget_add(provider_id: str | None, monthly_limit: float, alert_threshold: float, action_on_exceed: str):
    """Add a budget rule."""
    from ..db import SessionLocal, init_db
    from ..models.budget import BudgetRule

    init_db()
    db = SessionLocal()
    try:
        rule = BudgetRule(
            provider_id=provider_id, monthly_limit=monthly_limit,
            alert_threshold=alert_threshold, action_on_exceed=action_on_exceed,
        )
        db.add(rule)
        db.commit()
        scope = provider_id or "global"
        click.echo(f"✔ Budget rule added: ${monthly_limit:.2f}/mo for {scope} (action: {action_on_exceed})")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Orchestration commands
# ---------------------------------------------------------------------------


@cli.group()
def orchestrate():
    """Cross-cloud orchestration workflows."""
    pass


@orchestrate.command("vm-dns")
@click.option("--vm-provider", required=True, help="VM provider ID")
@click.option("--dns-provider", required=True, help="DNS provider ID")
@click.option("--vm-name", required=True, help="VM display name")
@click.option("--vm-type", default="instance", help="VM resource type")
@click.option("--zone-id", required=True, help="DNS zone ID")
@click.option("--record-name", required=True, help="DNS record name (e.g. app.example.com)")
def orchestrate_vm_dns(vm_provider: str, dns_provider: str, vm_name: str,
                       vm_type: str, zone_id: str, record_name: str):
    """Provision a VM and create a DNS record pointing to it."""
    from rich.console import Console
    from ..db import SessionLocal, init_db
    from ..services.orchestrator import OrchestratorService
    from ..services.registry import registry
    from ..app import _register_adapters

    _register_adapters()
    init_db()
    console = Console()
    db = SessionLocal()
    try:
        orch = OrchestratorService(registry, db)
        result = orch.provision_vm_with_dns(
            vm_provider_id=vm_provider, dns_provider_id=dns_provider,
            vm_config={"display_name": vm_name, "resource_type": vm_type},
            zone_id=zone_id, record_name=record_name,
        )
        for step in result.get("steps", []):
            icon = "✔" if step.get("status") == "ok" else "✗"
            console.print(f"  {icon} {step.get('step', '')}: {step.get('detail', '')}")
    finally:
        db.close()


@orchestrate.command("lockdown")
@click.argument("provider_id")
def orchestrate_lockdown(provider_id: str):
    """Emergency lockdown — stop all non-critical resources for a provider."""
    from rich.console import Console
    from ..db import SessionLocal, init_db
    from ..services.orchestrator import OrchestratorService
    from ..services.registry import registry
    from ..app import _register_adapters

    _register_adapters()
    init_db()
    console = Console()
    db = SessionLocal()
    try:
        orch = OrchestratorService(registry, db)
        result = orch.lockdown(provider_id)
        console.print(f"[bold]Lockdown complete:[/bold] {result.get('stopped', 0)} stopped, {result.get('skipped', 0)} skipped")
        for step in result.get("steps", []):
            console.print(f"  • {step}")
    finally:
        db.close()


@orchestrate.command("dns-failover")
@click.option("--resource-id", required=True, help="Resource ID to failover")
@click.option("--dns-provider", required=True, help="DNS provider ID")
@click.option("--zone-id", required=True, help="DNS zone ID")
@click.option("--record-id", required=True, help="DNS record ID to update")
@click.option("--new-ip", required=True, help="New IP address")
@click.option("--record-name", required=True, help="DNS record name")
def orchestrate_dns_failover(resource_id: str, dns_provider: str, zone_id: str,
                              record_id: str, new_ip: str, record_name: str):
    """Update DNS to failover to a new IP."""
    from rich.console import Console
    from ..db import SessionLocal, init_db
    from ..services.orchestrator import OrchestratorService
    from ..services.registry import registry
    from ..app import _register_adapters

    _register_adapters()
    init_db()
    console = Console()
    db = SessionLocal()
    try:
        orch = OrchestratorService(registry, db)
        result = orch.dns_failover(
            resource_id=resource_id, dns_provider_id=dns_provider,
            zone_id=zone_id, record_id=record_id,
            new_ip=new_ip, record_name=record_name,
        )
        for step in result.get("steps", []):
            icon = "✔" if step.get("status") == "ok" else "✗"
            console.print(f"  {icon} {step.get('step', '')}: {step.get('detail', '')}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Provision command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("provider_id")
@click.option("--type", "resource_type", default="instance", help="Resource type to provision")
@click.option("--name", "display_name", required=True, help="Resource display name")
@click.option("--config", "config_json", default="{}", help="JSON config for provisioning")
def provision(provider_id: str, resource_type: str, display_name: str, config_json: str):
    """Provision a new resource on a cloud provider."""
    import json
    from rich.console import Console
    from ..db import SessionLocal, init_db
    from ..services.registry import registry
    from ..app import _register_adapters

    _register_adapters()
    init_db()
    console = Console()
    db = SessionLocal()
    try:
        config = json.loads(config_json)
        config["display_name"] = display_name
        config["resource_type"] = resource_type

        adapter = registry.get_adapter(provider_id, db)
        result = adapter.provision(config)
        console.print(f"[green]✔ Provisioned:[/green] {result}")
    except Exception as e:
        console.print(f"[red]✗ Provision failed:[/red] {e}")
        raise SystemExit(1)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Backup commands
# ---------------------------------------------------------------------------


@cli.group()
def backup():
    """Database backup management."""
    pass


@backup.command("create")
def backup_create():
    """Create a database backup with automatic rotation."""
    from ..services.backup import backup_database
    result = backup_database()
    if "error" in result:
        click.echo(f"✗ {result['error']}", err=True)
        raise SystemExit(1)
    click.echo(f"✔ Backup created: {result['path']} ({result['size_bytes']} bytes)")
    if result.get("rotated_out"):
        click.echo(f"  Rotated out: {', '.join(result['rotated_out'])}")
    click.echo(f"  Total backups: {result['total_backups']}")


@backup.command("list")
def backup_list():
    """List existing database backups."""
    from rich.console import Console
    from rich.table import Table
    from ..services.backup import list_backups

    backups = list_backups()
    if not backups:
        click.echo("No backups found.")
        return

    console = Console()
    table = Table(title="Database Backups")
    table.add_column("Name")
    table.add_column("Size", justify="right")
    table.add_column("Created")

    for b in backups:
        size_kb = b["size_bytes"] / 1024
        table.add_row(b["name"], f"{size_kb:.1f} KB", b["created"])

    console.print(table)


if __name__ == "__main__":
    cli()
