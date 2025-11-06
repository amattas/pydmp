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
from .const.strings import AREA_STATUS, ZONE_STATUS, OUTPUT_STATUS
from .status_parser import parse_s3_message

console = Console()


def _fmt_ddmmyy(value: str | None) -> str:
    """Format DDMMYY into a human-readable date like '31 Jul 2025'.

    Returns empty string for None/invalid/zeros.
    """
    if not value or len(value) != 6 or not value.isdigit() or value == "000000":
        return ""
    dd = int(value[0:2])
    mm = int(value[2:4])
    yy = int(value[4:6])
    # Map YY to year: 00-79 => 2000-2079, 80-99 => 1980-1999
    year = 2000 + yy if yy <= 79 else 1900 + yy
    try:
        import datetime as _dt
        dt = _dt.date(year, mm, dd)
        return dt.strftime("%d %b %Y")
    except Exception:
        return ""


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


# removed: get-status (use get-areas and get-zones)


@cli.command("arm")
@click.argument("areas", type=str)
@click.option("--bypass-faulted", is_flag=True, help="Bypass faulted zones")
@click.option("--force-arm", is_flag=True, help="Force arm bad zones")
@click.option("--instant/--no-instant", default=None, help="Remove entry/exit delays")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def arm_cmd(ctx: click.Context, areas: str, bypass_faulted: bool, force_arm: bool, instant: Optional[bool], as_json: bool) -> None:
    """Arm one or more areas, e.g. "1,2,3"."""
    area_list = [int(a.strip()) for a in areas.split(",") if a.strip()]
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            if not as_json:
                console.print(f"[cyan]Arming areas {area_list} (bypass={bypass_faulted}, force={force_arm}, instant={instant})...[/cyan]")
            await panel.arm_areas(area_list, bypass_faulted=bypass_faulted, force_arm=force_arm, instant=instant)
            if not as_json:
                console.print(f"[green]Areas {area_list} armed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "arm", "areas": area_list, "bypass_faulted": bypass_faulted, "force_arm": force_arm, "instant": instant}))
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


@cli.command("set-zone-bypass")
@click.argument("zone", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def set_zone_bypass(ctx: click.Context, zone: int, as_json: bool) -> None:
    """Bypass a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            if not as_json:
                console.print(f"[cyan]Bypassing zone {zone}...[/cyan]")
            # Send direct command without forcing a status fetch
            resp = await panel._connection.send_command(DMPCommand.BYPASS_ZONE.value, zone=f"{zone:03d}")
            if resp == "NAK":
                detail = panel._connection.protocol.last_nak_detail or ""
                reason = ""
                if len(detail) == 2 and detail[1] == "U":
                    reason = " (undefined)"
                msg = f"Panel NAK (-{detail or 'X'}): bypass zone {zone}{reason}"
                if as_json:
                    click.echo(json.dumps({"ok": False, "error": msg}))
                else:
                    console.print(f"[red]{msg}[/red]")
                raise SystemExit(1)
            if not as_json:
                console.print(f"[green]Zone {zone} bypassed successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "set-zone-bypass", "zone": zone}))
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("set-zone-restore")
@click.argument("zone", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def set_zone_restore(ctx: click.Context, zone: int, as_json: bool) -> None:
    """Restore (un-bypass) a zone."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            if not as_json:
                console.print(f"[cyan]Restoring zone {zone}...[/cyan]")
            # Send direct command without forcing a status fetch
            resp = await panel._connection.send_command(DMPCommand.RESTORE_ZONE.value, zone=f"{zone:03d}")
            if resp == "NAK":
                detail = panel._connection.protocol.last_nak_detail or ""
                reason = ""
                if len(detail) == 2 and detail[1] == "U":
                    reason = " (undefined)"
                msg = f"Panel NAK (-{detail or 'Y'}): restore zone {zone}{reason}"
                if as_json:
                    click.echo(json.dumps({"ok": False, "error": msg}))
                else:
                    console.print(f"[red]{msg}[/red]")
                raise SystemExit(1)
            if not as_json:
                console.print(f"[green]Zone {zone} restored successfully[/green]")
            else:
                click.echo(json.dumps({"ok": True, "action": "set-zone-restore", "zone": zone}))
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


# removed: arm-areas (use 'arm')


# removed: disarm-areas (use multiple calls to 'disarm' or add back if needed)


@cli.command("get-users")
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
                        _fmt_ddmmyy(u.start_date),
                        _fmt_ddmmyy(u.end_date),
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


@cli.command("get-profiles")
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
                table.add_column("Areas", style="yellow")
                table.add_column("Access Areas", style="yellow")
                table.add_column("Menu", style="yellow")
                table.add_column("Rearm", style="yellow")
                for p in profiles:
                    table.add_row(
                        p.number,
                        p.name or "",
                        p.output_group,
                        p.areas_mask,
                        p.access_areas_mask,
                        p.menu_options,
                        p.rearm_delay,
                    )
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


@cli.command("get-outputs")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def list_outputs(ctx: click.Context, as_json: bool) -> None:
    """List outputs (1-4) and last-known state."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        panel = DMPPanel()
        try:
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"]) 
            # Fetch current status
            await panel.update_output_status()
            outputs = await panel.get_outputs()
            if not as_json:
                table = Table(title="Outputs")
                table.add_column("Number", style="cyan")
                table.add_column("Name", style="magenta")
                table.add_column("Code", style="yellow")
                table.add_column("State", style="yellow")
                for o in outputs:
                    code = o.state
                    text = OUTPUT_STATUS.get(code, code)
                    table.add_row(str(o.number), o.name or f"Output {o.number}", code, text)
                console.print(table)
            else:
                click.echo(json.dumps({"ok": True, "outputs": [o.to_dict() for o in outputs]}))
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


@cli.command("get-areas")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def get_areas_cmd(ctx: click.Context, as_json: bool) -> None:
    """List areas and their state."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            if not as_json:
                console.print("[cyan]Connecting to panel...[/cyan]")
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            await panel.update_status()
            areas = await panel.get_areas()
            if as_json:
                payload = {"ok": True, "areas": [a.to_dict() for a in areas]}
                click.echo(json.dumps(payload))
                return
            table = Table(title="Areas")
            table.add_column("Number", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("State", style="yellow")
            for area in areas:
                state_style = "green" if area.is_disarmed else "red"
                state_text = AREA_STATUS.get(area.state, area.state)
                table.add_row(str(area.number), area.name, f"[{state_style}]{state_text}[/{state_style}]")
            console.print(table)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("get-zones")
@click.option("--json", "as_json", is_flag=True, help="Output JSON instead of text")
@click.pass_context
def get_zones_cmd(ctx: click.Context, as_json: bool) -> None:
    """List zones and their state."""
    config = ctx.obj["config"]
    panel_config = config.get("panel", {})

    async def run():
        pc = panel_config
        panel = DMPPanel(port=int(pc.get("port", DEFAULT_PORT)), timeout=float(pc.get("timeout", 10.0)))
        try:
            if not as_json:
                console.print("[cyan]Connecting to panel...[/cyan]")
            await panel.connect(panel_config["host"], panel_config["account"], panel_config["remote_key"])
            await panel.update_status()
            zones = await panel.get_zones()
            if as_json:
                payload = {"ok": True, "zones": [z.to_dict() for z in zones]}
                click.echo(json.dumps(payload))
                return
            table = Table(title="Zones")
            table.add_column("Number", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("Code", style="yellow")
            table.add_column("State", style="yellow")
            table.add_column("Bypassed", style="yellow")
            table.add_column("Fault", style="yellow")
            for zone in zones:
                state_style = "green" if zone.is_normal else "red"
                state_text = ZONE_STATUS.get(zone.state, zone.state)
                bypassed = "Y" if zone.is_bypassed else ""
                fault = "Y" if zone.has_fault else ""
                table.add_row(str(zone.number), zone.name, zone.state, f"[{state_style}]{state_text}[/{state_style}]", bypassed, fault)
            console.print(table)
        finally:
            await panel.disconnect()

    asyncio.run(run())


@cli.command("set-output")
@click.argument("output", type=int)
@click.argument("action", type=click.Choice(["on", "off", "pulse", "toggle"]))
@click.pass_context
def set_output(ctx: click.Context, output: int, action: str) -> None:
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


# removed: 'outputs' alias; use 'get-outputs'


# (removed duplicate alias commands for set-zone-bypass and set-zone-restore)


# (removed legacy arm command with away/stay modes)
def main() -> None:
    """CLI entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
