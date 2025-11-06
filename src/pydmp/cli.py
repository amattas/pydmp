"""Command-line interface for PyDMP."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Any

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
from .const.protocol import DEFAULT_PORT
from .status_server import DMPStatusServer
from .const.strings import AREA_STATUS, ZONE_STATUS
from .status_parser import parse_s3_message

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
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[red]Error parsing config: {e}[/red]")
        sys.exit(1)
    # Normalize common shapes
    cfg = _normalize_config(raw)
    if cfg is None:
        console.print(
            "[red]Invalid config. Expected mapping with 'panel' section, e.g.\n"
            "panel:\n  host: 192.168.1.100\n  account: '00001'\n  remote_key: 'YOURKEY'[/red]"
        )
        sys.exit(1)
    return cfg


def _normalize_config(raw: Any) -> dict | None:
    """Normalize YAML into a dict with a 'panel' mapping.

    Accepts these shapes:
    - {panel: {host, account, remote_key}}
    - {host, account, remote_key}
    - [{...}] (list with a single mapping)
    Returns None if unknown.
    """
    data = raw
    if isinstance(raw, list) and raw:
        data = raw[0]
    if not isinstance(data, dict):
        return None
    if "panel" in data and isinstance(data["panel"], dict):
        # Coerce types
        p = data["panel"]
        if not {"host", "account"}.issubset(p.keys()):
            return None
        p = {
            "host": str(p.get("host", "")),
            "account": str(p.get("account", "")),
            "remote_key": str(p.get("remote_key", "")),
            "port": int(p.get("port", DEFAULT_PORT)) if str(p.get("port", "")).strip() != "" else DEFAULT_PORT,
            "timeout": float(p.get("timeout", 10.0)),
        }
        return {"panel": p}
    # Top-level keys
    if {"host", "account"}.issubset(data.keys()):
        p = {
            "host": str(data.get("host", "")),
            "account": str(data.get("account", "")),
            "remote_key": str(data.get("remote_key", "")),
            "port": int(data.get("port", DEFAULT_PORT)) if str(data.get("port", "")).strip() != "" else DEFAULT_PORT,
            "timeout": float(data.get("timeout", 10.0)),
        }
        return {"panel": p}
    return None


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
@click.option("--json", "as_json", is_flag=True, help="Output status as JSON")
@click.pass_context
def status(ctx: click.Context, as_json: bool) -> None:
    """Get panel status (areas and zones)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            if not as_json:
                console.print("[cyan]Connecting to panel...[/cyan]")
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )

            if not as_json:
                console.print("[green]Connected![/green]\n")

            # Fetch
            areas = await panel.get_areas()
            zones = await panel.get_zones()

            if as_json:
                payload = {"ok": True, "areas": [a.to_dict() for a in areas], "zones": [z.to_dict() for z in zones]}
                click.echo(json.dumps(payload))
                return

            # Human-readable tables
            if areas:
                table = Table(title="Areas")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("State", style="yellow")

                for area in areas:
                    state_style = "green" if area.is_disarmed else "red"
                    state_text = AREA_STATUS.get(area.state, area.state)
                    table.add_row(
                        str(area.number), area.name, f"[{state_style}]{state_text}[/{state_style}]"
                    )

                console.print(table)
                console.print()

            if zones:
                table = Table(title="Zones")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("State", style="yellow")

                for zone in zones:
                    state_style = "green" if zone.is_normal else "red"
                    state_text = ZONE_STATUS.get(zone.state, zone.state)
                    table.add_row(
                        str(zone.number), zone.name, f"[{state_style}]{state_text}[/{state_style}]"
                    )

                console.print(table)

        except Exception as e:
            # If JSON requested, emit structured error; otherwise styled message
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def arm_away(ctx: click.Context, area: int, bypass_faulted: bool, force_arm: bool, as_json: bool) -> None:
    """Arm area in away mode."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            area_obj = await panel.get_area(area)
            if not as_json:
                console.print(f"[cyan]Arming area {area} (bypass={bypass_faulted}, force={force_arm})...[/cyan]")
            await area_obj.arm_away(bypass_faulted=bypass_faulted, force_arm=force_arm)
            if not as_json:
                console.print(f"[green]Area {area} armed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "arm_away", "area": area, "bypass_faulted": bypass_faulted, "force_arm": force_arm}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def arm_stay(ctx: click.Context, area: int, bypass_faulted: bool, force_arm: bool, as_json: bool) -> None:
    """Arm area in stay mode."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            area_obj = await panel.get_area(area)
            if not as_json:
                console.print(f"[cyan]Arming area {area} (stay, bypass={bypass_faulted}, force={force_arm})...[/cyan]")
            await area_obj.arm_stay(bypass_faulted=bypass_faulted, force_arm=force_arm)
            if not as_json:
                console.print(f"[green]Area {area} armed (stay) successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "arm_stay", "area": area, "bypass_faulted": bypass_faulted, "force_arm": force_arm}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("area", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def disarm(ctx: click.Context, area: int, as_json: bool) -> None:
    """Disarm area."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            area_obj = await panel.get_area(area)
            if not as_json:
                console.print(f"[cyan]Disarming area {area}...[/cyan]")
            await area_obj.disarm()
            if not as_json:
                console.print(f"[green]Area {area} disarmed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "disarm", "area": area}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("zone", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def bypass_zone(ctx: click.Context, zone: int, as_json: bool) -> None:
    """Bypass a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            zone_obj = await panel.get_zone(zone)
            if not as_json:
                console.print(f"[cyan]Bypassing zone {zone}...[/cyan]")
            await zone_obj.bypass()
            if not as_json:
                console.print(f"[green]Zone {zone} bypassed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "bypass_zone", "zone": zone}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("zone", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def restore_zone(ctx: click.Context, zone: int, as_json: bool) -> None:
    """Restore (un-bypass) a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            zone_obj = await panel.get_zone(zone)
            if not as_json:
                console.print(f"[cyan]Restoring zone {zone}...[/cyan]")
            await zone_obj.restore()
            if not as_json:
                console.print(f"[green]Zone {zone} restored successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "restore_zone", "zone": zone}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command()
@click.argument("output", type=int)
@click.argument("action", type=click.Choice(["on", "off", "pulse", "toggle"]))
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def output(ctx: click.Context, output: int, action: str, as_json: bool) -> None:
    """Control an output."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(
                panel_config["host"], panel_config["account"], panel_config["remote_key"]
            )
            output_obj = await panel.get_output(output)
            if not as_json:
                console.print(f"[cyan]Setting output {output} to {action}...[/cyan]")

            if action == "on":
                await output_obj.turn_on()
            elif action == "off":
                await output_obj.turn_off()
            elif action == "pulse":
                await output_obj.pulse()
            elif action == "toggle":
                await output_obj.toggle()

            if not as_json:
                console.print(f"[green]Output {output} {action} successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "output", "output": output, "mode": action}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("arm-areas")
@click.argument("areas", type=str)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.option("--instant/--no-instant", default=None, help="Remove entry/exit delays")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def arm_areas_cmd(
    ctx: click.Context,
    areas: str,
    bypass_faulted: bool,
    force_arm: bool,
    instant: Optional[bool],
    as_json: bool,
) -> None:
    """Arm one or more areas, e.g. "1,2,3"."""
    area_list = [int(a.strip()) for a in areas.split(",") if a.strip()]
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            if not as_json:
                console.print(
                    f"[cyan]Arming areas {area_list} (bypass={bypass_faulted}, force={force_arm}, instant={instant})...[/cyan]"
                )
            await panel.arm_areas(area_list, bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant)
            if not as_json:
                console.print(f"[green]Areas {area_list} armed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "arm_areas", "areas": area_list, "bypass_faulted": bypass_faulted, "force_arm": force_arm, "instant": instant}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("disarm-areas")
@click.argument("areas", type=str)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def disarm_areas_cmd(ctx: click.Context, areas: str, as_json: bool) -> None:
    """Disarm one or more areas, e.g. "1,2,3"."""
    area_list = [int(a.strip()) for a in areas.split(",") if a.strip()]
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"]) 
            if not as_json:
                console.print(f"[cyan]Disarming areas {area_list}...[/cyan]")
            await panel.disarm_areas(area_list)
            if not as_json:
                console.print(f"[green]Areas {area_list} disarmed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "disarm_areas", "areas": area_list}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("users")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_users(ctx: click.Context, as_json: bool) -> None:
    """List panel user codes (decrypted)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"]) 
            users = await panel.get_user_codes()
            if not as_json:
                table = Table(title="Users")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("Code", style="yellow")
                table.add_column("PIN", style="yellow")
                table.add_column("Start", style="yellow")
                table.add_column("End", style="yellow")
                table.add_column("Flags", style="yellow")
                for u in users:
                    table.add_row(
                        u.number,
                        u.name or "",
                        u.code,
                        u.pin,
                        (u.start_date or ""),
                        (u.end_date or ""),
                        (u.flags or ""),
                    )
                console.print(table)
            else:
                from dataclasses import asdict
                click.echo(json.dumps({"ok": True, "users": [asdict(u) for u in users]}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("profiles")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_profiles(ctx: click.Context, as_json: bool) -> None:
    """List user profiles."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"]) 
            profiles = await panel.get_user_profiles()
            if not as_json:
                table = Table(title="Profiles")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("Output Group", style="yellow")
                for p in profiles:
                    table.add_row(p.number, p.name or "", p.output_group)
                console.print(table)
            else:
                from dataclasses import asdict
                click.echo(json.dumps({"ok": True, "profiles": [asdict(p) for p in profiles]}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("sensor-reset")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def sensor_reset(ctx: click.Context, as_json: bool) -> None:
    """Send sensor reset (!E001)."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"]) 
            if not as_json:
                console.print("[cyan]Sending sensor reset...[/cyan]")
            await panel.sensor_reset()
            if not as_json:
                console.print("[green]Sensor reset sent[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "sensor_reset"}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("check-code")
@click.argument("code", type=str)
@click.option("--include-pin/--no-include-pin", default=True, show_default=True, help="Match PIN as well as code")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def check_code_cmd(ctx: click.Context, code: str, include_pin: bool, as_json: bool) -> None:
    """Check if a code or PIN exists in the panel."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            user = await panel.check_code(code, include_pin=include_pin)
            if not as_json:
                if user:
                    console.print(f"[green]MATCH[/green]: number={user.number} name={user.name}")
                else:
                    console.print("[red]No match[/red]")
            else:
                from dataclasses import asdict
                click.echo(json.dumps({"ok": True, "found": bool(user), "user": (asdict(user) if user else None)}))
        except Exception as e:
            if as_json:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("listen")
@click.option("--host", default="0.0.0.0", show_default=True, help="Listen host")
@click.option("--port", default=5001, show_default=True, type=int, help="Listen port")
@click.option("--duration", default=0, type=int, help="Seconds to run (0=until Ctrl+C)")
@click.option("--json", "as_json", is_flag=True, help="Output events as JSON (NDJSON)")
def listen(host: str, port: int, duration: int, as_json: bool) -> None:
    """Run realtime S3 status server and print parsed events."""

    async def run():
        server = DMPStatusServer(host=host, port=port)

        def on_event(msg):
            evt = parse_s3_message(msg)
            if not as_json:
                console.print(f"[blue]{evt.category}[/blue] {evt.type_code} a={evt.area} z={evt.zone} v={evt.device} {evt.system_text or ''}")
            else:
                from dataclasses import asdict
                # Emit newline-delimited JSON events
                click.echo(json.dumps(asdict(evt)))

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
