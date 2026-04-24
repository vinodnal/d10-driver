# D10 Driver

A modular, production-ready Python driver for the **Bio-Rad D-10 Hemoglobin Analyzer** (and other ASTM-compatible laboratory instruments).

## Features

- **Standards-compliant ASTM E1381/E1394 protocol** — correct framing, checksum validation, ACK/NAK handshake, and retransmission.
- **Modular design** — communication, protocol, parsing, and persistence are completely independent and interchangeable.
- **Multiple transports** — RS-232 serial (default) and TCP/IP socket.
- **MySQL persistence** — full relational schema for messages, patients, orders, and results with referential integrity.
- **Comprehensive logging** — rotating file logs (full DEBUG trace) plus coloured console output.
- **Terminal CLI** — `start`, `init-db`, `query`, `show-config` commands.
- **Extensible** — add new instrument parsers or database back-ends without touching existing code.
- **95 automated tests** covering protocol framing, parsing, models, and configuration.

## Architecture

```
d10_driver/
├── config/            # YAML-based settings with env-var overrides
├── communication/     # Abstract base + Serial and TCP transports
├── protocol/          # ASTM E1381 frame reader/writer and constants
├── parsers/           # Abstract base + D-10 specific ASTM E1394 parser
├── models/            # Domain models: ASTMMessage, PatientRecord, OrderRecord, ResultRecord
├── database/          # Abstract base + MySQL repository
├── logging_utils/     # Rotating file log + coloured console handler
├── cli/               # Click-based terminal interface
├── driver.py          # Main orchestrator
└── main.py            # Entry point
tests/
├── test_astm_protocol.py   # Frame building, checksum, reader/writer round-trip
├── test_d10_parser.py      # Full parser coverage (header, patient, order, result, terminator)
├── test_models.py          # Data model property helpers
└── test_config.py          # Settings loading, YAML merge, env-var overrides
```

## Protocol Compliance

The driver implements **ASTM E1381** (low-level framing) and **ASTM E1394** (high-level message content):

| Layer | Standard | Details |
|-------|----------|---------|
| Physical | RS-232 | 9600 baud, 8N1 (default, configurable) |
| Framing | ASTM E1381 | STX/ETX/ETB frames, frame numbers 1–7 cycling, 2-char hex checksum |
| Handshake | ASTM E1381 | ENQ→ACK, per-frame ACK/NAK, EOT |
| Content | ASTM E1394 | H/P/O/R/L records, `|` field separator, `^` component separator |

## Quick Start

### 1. Install

[uv](https://docs.astral.sh/uv/) is the project's package manager. Install it once, then sync the project:

```bash
# Install uv (if not already installed)
pip install uv          # or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync all runtime + dev dependencies into an isolated virtual environment
uv sync --group dev
```

For a runtime-only install (no test dependencies):

```bash
uv sync
```

The `d10-driver` CLI is automatically available inside the venv managed by uv.

### 2. Configure

```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your serial port and database credentials
```

### 3. Initialise the database

```bash
uv run d10-driver init-db
```

### 4. Start the driver

```bash
# Serial port (default)
uv run d10-driver start

# Override port and baud rate
uv run d10-driver start --port /dev/ttyS0 --baud-rate 19200

# TCP/IP transport (for instruments with Ethernet interface)
uv run d10-driver start --tcp-host 192.168.1.50 --tcp-port 5000

# Log-only mode (no database)
uv run d10-driver start --no-db
```

### 5. Query results

```bash
# By specimen ID
uv run d10-driver query --specimen-id SPEC001

# By patient ID
uv run d10-driver query --patient-id PAT001
```

### 6. Show active configuration

```bash
uv run d10-driver show-config
```


## Environment Variables

Any setting can be overridden without editing the config file:

```bash
export D10_SERIAL_PORT=/dev/ttyS1
export D10_DATABASE_HOST=db.example.com
export D10_DATABASE_PASSWORD=secret
export D10_DRIVER_AUTO_COMMIT=false
d10-driver start
```

Pattern: `D10_<SECTION>_<KEY>=value`

## Database Schema

```sql
d10_messages  — one row per ASTM transmission (H/L pair)
d10_patients  — patient demographics (P records)
d10_orders    — test orders (O records)
d10_results   — analyte results (R records, one per haemoglobin fraction)
```

Foreign keys cascade on delete, and all tables have indexes on the most common query columns.

## Adding a New Instrument Parser

1. Subclass `BaseParser` in a new module under `d10_driver/parsers/`.
2. Implement `parse_message(records)` → `ASTMMessage`.
3. Pass your parser to `D10Driver(transport, parser=MyParser())`.

No other code changes are required.

## Adding a New Database Back-end

1. Subclass `BaseRepository` in a new module under `d10_driver/database/`.
2. Implement `connect`, `disconnect`, `create_schema`, `save_message`, `find_results_by_specimen`, `find_messages_by_patient`.
3. Pass your repository to `D10Driver(transport, repository=MyRepository())`.

## Running Tests

```bash
uv run --group dev pytest tests/ -v
```

## Logging

- **File logs** — written to `logs/d10_driver.log` (rotating, 10 MB max, 5 backups).
- **Console** — INFO level by default; use `-v` flag for DEBUG.
- Full ASTM frame traces (hex dumps) at DEBUG level enable complete protocol traceability.

## Requirements

- Python ≥ 3.9
- [uv](https://docs.astral.sh/uv/) (manages all other dependencies)

Runtime dependencies (declared in `pyproject.toml`, pinned in `uv.lock`):
- pyserial ≥ 3.5
- mysql-connector-python ≥ 8.0, < 9
- PyYAML ≥ 6.0
- click ≥ 8.1
- tabulate ≥ 0.9
- colorlog ≥ 6.7
