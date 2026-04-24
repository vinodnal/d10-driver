"""
Terminal / CLI management interface for the D10 driver.

This module provides an interactive command-line interface built on top of
the `click` library.  Commands cover:

- ``start``    — run the driver and listen for instrument data.
- ``status``   — display current driver statistics.
- ``query``    — query results stored in the database.
- ``init-db``  — initialise the database schema.
- ``show-config`` — display the active configuration.

Usage
-----
::

    # Via the installed console script:
    d10-driver start --port /dev/ttyUSB0

    # Or directly:
    python -m d10_driver.main start --help
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from d10_driver.config.settings import load_settings, get_settings
from d10_driver.logging_utils.logger import configure_logging, get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="Run 'd10-driver COMMAND --help' for command-specific help.",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    default="config.yaml",
    show_default=True,
    help="Path to the YAML configuration file.",
    type=click.Path(dir_okay=False),
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose (DEBUG-level) console output.",
)
@click.pass_context
def cli(ctx: click.Context, config_path: str, verbose: bool) -> None:
    """D10 Driver — Bio-Rad D-10 hemoglobin analyzer interface.

    Communicates with the instrument via ASTM E1381/E1394 protocol and
    persists results to a MySQL database.
    """
    ctx.ensure_object(dict)

    # Load settings first so logging can pick up the configured log dir
    settings = load_settings(config_path)

    console_level = logging.DEBUG if verbose else logging.INFO
    configure_logging(
        log_level=logging.DEBUG,
        console_level=console_level,
        log_dir=settings.logging.log_dir,
    )
    ctx.obj["settings"] = settings


# ---------------------------------------------------------------------------
# start command
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--port",
    default=None,
    help="Serial port (overrides config file).",
)
@click.option(
    "--baud-rate",
    default=None,
    type=int,
    help="Baud rate (overrides config file).",
)
@click.option(
    "--tcp-host",
    default=None,
    help="Use TCP transport instead of serial (host address).",
)
@click.option(
    "--tcp-port",
    default=None,
    type=int,
    help="TCP port number (used with --tcp-host).",
)
@click.option(
    "--no-db",
    is_flag=True,
    default=False,
    help="Disable database persistence (log-only mode).",
)
@click.pass_context
def start(
    ctx: click.Context,
    port: Optional[str],
    baud_rate: Optional[int],
    tcp_host: Optional[str],
    tcp_port: Optional[int],
    no_db: bool,
) -> None:
    """Start the driver and begin receiving instrument data.

    The driver runs until interrupted with Ctrl+C.
    """
    import signal

    from d10_driver.driver import D10Driver

    settings = ctx.obj["settings"]
    serial_cfg = settings.serial
    db_cfg = settings.database
    driver_cfg = settings.driver

    # Build transport
    if tcp_host:
        from d10_driver.communication.tcp_protocol import TCPProtocol

        _port = tcp_port or 5000
        transport = TCPProtocol(host=tcp_host, port=_port, timeout=serial_cfg.timeout)
        click.echo(f"Using TCP transport: {tcp_host}:{_port}")
    else:
        from d10_driver.communication.serial_protocol import SerialProtocol

        _serial_port = port or serial_cfg.port
        _baud = baud_rate or serial_cfg.baud_rate
        transport = SerialProtocol(
            port=_serial_port,
            baud_rate=_baud,
            data_bits=serial_cfg.data_bits,
            parity=serial_cfg.parity,
            stop_bits=serial_cfg.stop_bits,
            timeout=serial_cfg.timeout,
        )
        click.echo(f"Using serial transport: {_serial_port} @ {_baud} baud")

    # Build repository
    repository = None
    if not no_db:
        from d10_driver.database.mysql_repository import MySQLRepository

        repository = MySQLRepository(
            host=db_cfg.host,
            port=db_cfg.port,
            user=db_cfg.user,
            password=db_cfg.password,
            database=db_cfg.database,
            instrument_id=driver_cfg.instrument_id,
        )
        click.echo(
            f"Database: {db_cfg.user}@{db_cfg.host}:{db_cfg.port}/{db_cfg.database}"
        )
    else:
        click.echo("Database persistence disabled (--no-db).")

    driver = D10Driver(
        transport,
        repository=repository,
        config=driver_cfg,
    )

    def _handle_signal(signum, frame):
        click.echo("\nShutdown signal received — stopping driver…")
        driver.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    click.secho(
        f"\nD10 Driver started (instrument_id={driver_cfg.instrument_id}). "
        "Press Ctrl+C to stop.\n",
        fg="green",
        bold=True,
    )

    try:
        driver.start(blocking=True)
    except SystemExit:
        pass
    finally:
        click.secho(
            f"\nDriver stopped — messages: {driver.message_count}, "
            f"errors: {driver.error_count}",
            fg="yellow",
        )


# ---------------------------------------------------------------------------
# init-db command
# ---------------------------------------------------------------------------


@cli.command("init-db")
@click.pass_context
def init_db(ctx: click.Context) -> None:
    """Initialise the MySQL database schema.

    Creates all required tables if they do not already exist.  Safe to run
    on an already-initialised database.
    """
    from d10_driver.database.mysql_repository import MySQLRepository

    settings = ctx.obj["settings"]
    db = settings.database
    driver_cfg = settings.driver

    click.echo(f"Connecting to {db.user}@{db.host}:{db.port}/{db.database}…")
    repo = MySQLRepository(
        host=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        database=db.database,
        instrument_id=driver_cfg.instrument_id,
    )
    try:
        repo.connect()
        repo.create_schema()
        click.secho("Database schema initialised successfully.", fg="green")
    except Exception as exc:
        click.secho(f"ERROR: {exc}", fg="red", err=True)
        sys.exit(1)
    finally:
        repo.disconnect()


# ---------------------------------------------------------------------------
# query command
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--specimen-id",
    "-s",
    default=None,
    help="Filter results by specimen ID.",
)
@click.option(
    "--patient-id",
    "-p",
    default=None,
    help="Filter results by patient ID.",
)
@click.option(
    "--limit",
    "-n",
    default=20,
    show_default=True,
    type=int,
    help="Maximum number of results to display.",
)
@click.pass_context
def query(
    ctx: click.Context,
    specimen_id: Optional[str],
    patient_id: Optional[str],
    limit: int,
) -> None:
    """Query results stored in the database.

    At least one of --specimen-id or --patient-id must be provided.
    """
    if not specimen_id and not patient_id:
        click.secho(
            "Error: provide at least one of --specimen-id or --patient-id.",
            fg="red",
            err=True,
        )
        sys.exit(1)

    from d10_driver.database.mysql_repository import MySQLRepository

    try:
        from tabulate import tabulate
    except ImportError:
        tabulate = None  # type: ignore[assignment]

    settings = ctx.obj["settings"]
    db = settings.database
    driver_cfg = settings.driver

    repo = MySQLRepository(
        host=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        database=db.database,
        instrument_id=driver_cfg.instrument_id,
    )
    try:
        repo.connect()

        if specimen_id:
            results = repo.find_results_by_specimen(specimen_id)[:limit]
            if not results:
                click.echo(f"No results found for specimen '{specimen_id}'.")
                return

            rows = [
                [
                    r.sequence_number,
                    r.analyte_name,
                    r.value,
                    r.units,
                    r.reference_ranges,
                    r.abnormal_flags or "—",
                    r.result_status,
                ]
                for r in results
            ]
            headers = ["#", "Analyte", "Value", "Units", "Ref. Range", "Flag", "Status"]

        elif patient_id:
            messages = repo.find_messages_by_patient(patient_id)[:limit]
            if not messages:
                click.echo(f"No messages found for patient '{patient_id}'.")
                return

            rows = [
                [
                    m.sender_name or "—",
                    m.processing_id or "—",
                    m.completion_code or "—",
                ]
                for m in messages
            ]
            headers = ["Sender", "Processing ID", "Completion"]

        if tabulate:
            click.echo(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
        else:
            click.echo("\t".join(headers))
            for row in rows:
                click.echo("\t".join(str(c) for c in row))

    except Exception as exc:
        click.secho(f"ERROR: {exc}", fg="red", err=True)
        sys.exit(1)
    finally:
        repo.disconnect()


# ---------------------------------------------------------------------------
# show-config command
# ---------------------------------------------------------------------------


@cli.command("show-config")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Display the active configuration (masks the database password)."""
    import dataclasses

    settings = ctx.obj["settings"]

    for section_name in ("serial", "database", "logging", "driver"):
        section = getattr(settings, section_name)
        click.secho(f"\n[{section_name}]", bold=True)
        for f in dataclasses.fields(section):
            value = getattr(section, f.name)
            if f.name == "password":
                value = "***" if value else "(empty)"
            click.echo(f"  {f.name} = {value}")
