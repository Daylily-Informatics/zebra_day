<p align="center">
  <strong>Zebra Day</strong><br>
  Internal printer, label-template, print-job, and lab-code service for Dayhoff.
</p>

<p align="center">
  <a href="docs/README.md">Docs</a> ·
  <a href="docs/major_refactor.md">Refactor notes</a> ·
  <a href="docs/tapdb_hard_migration_plan.md">TapDB migration</a>
</p>

## Overview

Zebra Day is the LSMC internal Zebra printer fleet service. It manages labs, printer discovery/status, label templates, rendered labels, print jobs, observations, and shared fleet state in TapDB.

Current Dayhoff pin: `8.0.10`. Current TapDB dependency: `daylily-tapdb @ ...@9.0.6`.

Zebra Day is LSMC-internal only in Dayhoff exposure policy.

## What It Does

| Capability | Current surface |
|---|---|
| Lab and printer fleet state | GUI/API/CLI surfaces and TapDB-backed records |
| Discovery and scan progress | Lab printer pages, scan progress UI, and simulator tests |
| Label templates and jobs | Template rendering, print jobs, and observation records |
| Barcode/EUID printing | Service APIs used by Bloom and operators where configured |
| TapDB object views | Mounted `/tapdb` surfaces for generic object inspection |

## How It Works

Zebra Day keeps printer and label state in TapDB-backed records and exposes the same fleet/template/job concepts through GUI, API, and CLI where implemented. Real hardware output is treated as an explicit live side effect; tests use simulator or mocked print paths.

## Quickstart

```bash
cd /Users/jmajor/projects/mega_dayhoff/repos_work/zebra_day
source ./activate <deploy-name>
zday --help
zday server start --port 8118
```

Use Dayhoff-generated service config and explicit TapDB config. Shared fleet state is TapDB-backed.

## CLI Interface

The primary CLI is `zday`. It uses `cli-core-yo`, global `--json`, and shared output helpers. CLI commands cover config/runtime, printer discovery, labels, templates, print jobs, and simulator/testing helpers.

Common command families:

| Family | Purpose |
|---|---|
| `zday config ...` | Create or inspect explicit deployment config. |
| `zday server ...` | Start the FastAPI GUI/API service. |
| `zday printers ...` | Scan, inspect, and test printers where exposed by CLI. |
| `zday templates/labels/jobs ...` | Manage label templates, render labels, and inspect print jobs where exposed by CLI. |
| simulator helpers | Run test printer behavior without real hardware. |

The CLI, API, and GUI should expose the same printer/fleet/template/label capabilities where those surfaces exist.

## GUI

Zebra Day exposes a FastAPI/Jinja GUI for labs, printers, scan progress, printer details, templates, jobs, and TapDB-backed object views. The mounted TapDB GUI at `/tapdb` is the generic object/EUID surface when configured.

Printer scanning should show progress and respect configured wait/rate limits. Discovery can use ZPL port `9100` and optional HTTP probes where configured.

## API

JSON API routes live under `zebra_day/web/routers/api.py`. HTML routes live under `zebra_day/web/routers/ui.py`. Health, readiness, auth, and observability routes are wired by the service runtime.

## Testing Info

Focused checks:

```bash
ruff check zebra_day tests
ruff format --check zebra_day tests
mypy zebra_day --ignore-missing-imports
pytest tests/ -v --tb=short
```

Deployed evidence should target `https://zebra-day.<deploy>.dev.lsmc.bio` and include login redirect, lab page, printer scan UI, printer detail, TapDB mount, and label rendering where safe.

## Technical Details, History, And Linkouts

- [`docs/README.md`](docs/README.md): current docs index.
- [`docs/major_refactor.md`](docs/major_refactor.md): refactor background.
- [`docs/tapdb_hard_migration_plan.md`](docs/tapdb_hard_migration_plan.md): TapDB migration notes.
- [`docs/plans/`](docs/plans/): active ledgers.
