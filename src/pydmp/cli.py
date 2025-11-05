"""Command-line interface for PyDMP."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

try:
    import click
    import yaml
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("CLI dependencies not installed. Install with: pip install pydmp[cli]")
    sys.exit(1)

from . import __version__
from .const.states import AreaState, ZoneState
from .panel import DMPPanel

console = Console()


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[red]Error parsing config: {e}[/red]")
        sys.exit(1)


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Configuration file path",
)
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: Path, debug: bool) -> None:
    """PyDMP - Control DMP alarm panels from command line."""
    # Setup logging
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Load config
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config) if config.exists() else {}
    ctx.obj["debug"] = debug


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Get panel status (areas and zones)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            console.print("[cyan]Connecting to panel...[/cyan]")
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            console.print("[green]Connected![/green]\n")

            # Areas
            areas = await panel.get_areas()
            if areas:
                table = Table(title="Areas")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("State", style="yellow")

                for area in areas:
                    state_style = "green" if area.is_disarmed else "red"
                    table.add_row(
                        str(area.number), area.name, f"[{state_style}]{area.state}[/{state_style}]"
                    )

                console.print(table)
                console.print()

            # Zones
            zones = await panel.get_zones()
            if zones:
                table = Table(title="Zones")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("State", style="yellow")

                for zone in zones:
                    state_style = "green" if zone.is_normal else "red"
                    table.add_row(
                        str(zone.number), zone.name, f"[{state_style}]{zone.state}[/{state_style}]"
                    )

                console.print(table)

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.pass_context
def arm_away(ctx: click.Context, area: int, bypass_faulted: bool, force_arm: bool) -> None:
    """Arm area in away mode."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            area_obj = await panel.get_area(area)
            console.print(f"[cyan]Arming area {area} (bypass={bypass_faulted}, force={force_arm})...[/cyan]")

            await area_obj.arm_away(bypass_faulted=bypass_faulted, force_arm=force_arm)
            console.print(f"[green]Area {area} armed successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.pass_context
def arm_stay(ctx: click.Context, area: int, bypass_faulted: bool, force_arm: bool) -> None:
    """Arm area in stay mode."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            area_obj = await panel.get_area(area)
            console.print(f"[cyan]Arming area {area} (stay, bypass={bypass_faulted}, force={force_arm})...[/cyan]")

            await area_obj.arm_stay(bypass_faulted=bypass_faulted, force_arm=force_arm)
            console.print(f"[green]Area {area} armed (stay) successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.pass_context
def disarm(ctx: click.Context, area: int) -> None:
    """Disarm area."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            area_obj = await panel.get_area(area)
            console.print(f"[cyan]Disarming area {area}...[/cyan]")

            await area_obj.disarm()
            console.print(f"[green]Area {area} disarmed successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("zone", type=int)
@click.pass_context
def bypass_zone(ctx: click.Context, zone: int) -> None:
    """Bypass a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            zone_obj = await panel.get_zone(zone)
            console.print(f"[cyan]Bypassing zone {zone}...[/cyan]")

            await zone_obj.bypass()
            console.print(f"[green]Zone {zone} bypassed successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("zone", type=int)
@click.pass_context
def restore_zone(ctx: click.Context, zone: int) -> None:
    """Restore (un-bypass) a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            zone_obj = await panel.get_zone(zone)
            console.print(f"[cyan]Restoring zone {zone}...[/cyan]")

            await zone_obj.restore()
            console.print(f"[green]Zone {zone} restored successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("output", type=int)
@click.argument("action", type=click.Choice(["on", "off", "pulse", "toggle"]))
@click.pass_context
def output(ctx: click.Context, output: int, action: str) -> None:
    """Control an output."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            output_obj = await panel.get_output(output)
            console.print(f"[cyan]Setting output {output} to {action}...[/cyan]")

            if action == "on":
                await output_obj.turn_on()
            elif action == "off":
                await output_obj.turn_off()
            elif action == "pulse":
                await output_obj.pulse()
            elif action == "toggle":
                await output_obj.toggle()

            console.print(f"[green]Output {output} {action} successfully[/green]")

        finally:
            await panel.disconnect()

    asyncio.run(run())


def main() -> None:
    """CLI entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
