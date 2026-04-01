# AGENTS.md — zebra_day Project Directives

## What This Repo Is

`zebra_day` is a Python library + CLI + web GUI for managing fleets of Zebra label printers.
It speaks ZPL over TCP (port 9100), provides a FastAPI web UI, and stores shared fleet state,
templates, label profiles, observations, and print jobs in `daylily-tapdb`.

## Architecture Quick Reference

| Layer | Key Files | Notes |
|-------|-----------|-------|
| CLI | `zebra_day/cli/__init__.py` | Built on `cli-core-yo` (`create_app(spec)` + plugin `register()` pattern) |
| Core | `zebra_day/client.py`, `zebra_day/printer_protocol.py`, `zebra_day/cmd_mgr.py` | TapDB-backed domain logic, remote API client, and raw printer protocol helpers |
| Storage | `zebra_day/client.py`, `config/tapdb_templates/` | TapDB is the only supported shared datastore |
| Web | `zebra_day/web/` | FastAPI app, Jinja2 templates in `zebra_day/templates/modern/` |
| Simulator | `zebra_day/simulator.py` | Mock ZPL printer for testing (TCP 9100 + HTTP) |
| Paths | `zebra_day/paths.py` | XDG Base Directory helpers |

## CLI Rules

- The CLI uses **cli-core-yo** as its foundation. All command modules expose a `register(registry, spec)` function.
- **Global `--json/-j` flag** lives on the root callback. Do NOT add per-command `--json` flags.
- Use `output.*` primitives (`heading`, `success`, `warning`, `error`, `action`, `detail`, `bullet`, `emit_json`, `print_text`) — never raw `print()` or `console.print()` for user-facing output.
- In JSON mode, `output.error()` and other display primitives are **auto-suppressed**. Use `output.emit_json()` to emit machine-readable payloads.
- Pin cli-core-yo, typer, and rich versions per `pyproject.toml` ranges.

## Testing

- **Framework**: `pytest` + `pytest-cov`
- **Coverage focus**: TapDB-backed runtime paths, auth flows, CLI surface, and Playwright E2E auth coverage
- **Run all**: `pytest tests/ -v --tb=short`
- **Run one file**: `pytest tests/test_cli.py -v`
- **Linting**: `ruff check zebra_day tests && ruff format --check zebra_day tests`
- **Type checking**: `mypy zebra_day --ignore-missing-imports`

## Quality Gates (must pass before merge)

```bash
ruff check zebra_day tests
ruff format --check zebra_day tests
mypy zebra_day --ignore-missing-imports
pytest tests/ -v --tb=short
```

## Config Format

- Deployment runtime config is **YAML** and deployment-scoped by filename.
- Shared fleet state is stored in TapDB only.
- JSON is the preferred interchange format for APIs and TapDB seed assets.

## Network Scanner

- Default discovery: **ZPL port 9100** (`~HI` query).
- Optional HTTP fallback via `scan_http_port` parameter.
- The `notes` field records discovery method: `"zpl"`, `"http(port)"`, or `"zpl+http(port)"`.

## Web UI

- FastAPI + Jinja2 templates in `zebra_day/templates/modern/`.
- API routes: `zebra_day/web/routers/api.py` (JSON), `zebra_day/web/routers/ui.py` (HTML).
- Default port: **8118**. HTTPS by default if mkcert certs exist.
- Follow the API documentation exposure rules from global `~/.augment/rules/01_http_https_api_rules.md`.

## Versioning

- `setuptools_scm` — no hardcoded version. Tags are `X.Y.Z` (no `v` prefix).
- `_version.py` is generated — do not edit or commit it.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ZEBRA_DAY_DEPLOYMENT_CODE` | `local` | Active deployment name |
| `ZEBRA_DAY_AUTH_MODE` | `cognito` | Runtime auth mode override; `none` is supported via global `--no-auth` |
| `tapdb.client_id` | `zebra-day` | TapDB client namespace in service config |
| `tapdb.database_name` | `zebra-day-<deployment>` | TapDB database namespace in service config |
| `tapdb.env` | `dev` | TapDB environment selector in service config |
| `tapdb.config_path` | deployment derived | Required TapDB config file path in service config |
| `INTERNAL_API_KEY` | _(none)_ | Optional bearer token for machine API clients |
| `AWS_PROFILE` | _(none)_ | Used for daycog/Cognito admin commands; never pass `"default"` explicitly |

## Do NOT

- Add per-command `--json` flags (use the global one).
- Use `datetime.UTC` (use `datetime.timezone.utc` for mypy compat).
- Use `console.print()` for user-facing output (use `output.*` primitives).
- Store real patient data or PHI in tests or examples.
- Edit `_version.py` manually.
