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
from .panel import DMPPanel
from .const.commands import DMPCommand
from .status_server import DMPStatusServer
from .status_parser import parse_scsvr_message

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


@cli.command("arm-areas")
@click.argument("areas", type=str)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.option("--instant/--no-instant", default=None, help="Remove entry/exit delays")
@click.pass_context
def arm_areas_cmd(
    ctx: click.Context,
    areas: str,
    bypass_faulted: bool,
    force_arm: bool,
    instant: Optional[bool],
) -> None:
    """Arm one or more areas, e.g. "1,2,3"."""
    area_list = [int(a.strip()) for a in areas.split(",") if a.strip()]
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            console.print(
                f"[cyan]Arming areas {area_list} (bypass={bypass_faulted}, force={force_arm}, instant={instant})...[/cyan]"
            )
            await panel.arm_areas(area_list, bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant)
            console.print(f"[green]Areas {area_list} armed successfully[/green]")
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("disarm-areas")
@click.argument("areas", type=str)
@click.pass_context
def disarm_areas_cmd(ctx: click.Context, areas: str) -> None:
    """Disarm one or more areas, e.g. "1,2,3"."""
    area_list = [int(a.strip()) for a in areas.split(",") if a.strip()]
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            console.print(f"[cyan]Disarming areas {area_list}...[/cyan]")
            await panel.disarm_areas(area_list)
            console.print(f"[green]Areas {area_list} disarmed successfully[/green]")
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("users")
@click.pass_context
def list_users(ctx: click.Context) -> None:
    """List panel user codes (decrypted)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            users = await panel.get_user_codes()
            table = Table(title="Users")
            table.add_column("Number", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("Code", style="yellow")
            table.add_column("PIN", style="yellow")
            for u in users:
                table.add_row(u.number, u.name or "", u.code, u.pin)
            console.print(table)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("profiles")
@click.pass_context
def list_profiles(ctx: click.Context) -> None:
    """List user profiles."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            profiles = await panel.get_user_profiles()
            table = Table(title="Profiles")
            table.add_column("Number", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("Output Group", style="yellow")
            for p in profiles:
                table.add_row(p.number, p.name or "", p.output_group)
            console.print(table)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("sensor-reset")
@click.pass_context
def sensor_reset(ctx: click.Context) -> None:
    """Send sensor reset (!E001)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            console.print("[cyan]Sending sensor reset...[/cyan]")
            resp = await panel._connection.send_command(DMPCommand.SENSOR_RESET.value)  # type: ignore[union-attr]
            console.print(f"[green]Response: {resp}[/green]")
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("listen")
@click.option("--host", default="0.0.0.0", show_default=True, help="Listen host")
@click.option("--port", default=5001, show_default=True, type=int, help="Listen port")
@click.option("--duration", default=0, type=int, help="Seconds to run (0=until Ctrl+C)")
def listen(host: str, port: int, duration: int) -> None:
    """Run realtime S3 status server and print parsed events."""

    async def run():
        server = DMPStatusServer(host=host, port=port)

        def on_event(msg):
            evt = parse_scsvr_message(msg)
            console.print(f"[blue]{evt.category}[/blue] {evt.type_code} a={evt.area} z={evt.zone} v={evt.device} {evt.system_text or ''}")

        server.register_callback(on_event)
        await server.start()
        if duration > 0:
            await asyncio.sleep(duration)
        else:
            try:
                while True:
                    await asyncio.sleep(3600)
            except KeyboardInterrupt:
                pass
        await server.stop()

    asyncio.run(run())


def main() -> None:
    """CLI entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
