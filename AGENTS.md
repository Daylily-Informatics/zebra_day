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

## Activate Contract

- `source ./activate <deploy-name>` is env setup only.
- `activate` may create the conda env if missing, activate it, and run exactly one `python -m pip install -e .` on first create.
- Do not add package installs, dependency probes, TapDB bootstrap, config copying, registry writes, loader-path hacks, or `conda install` steps to `activate`.
- If a CLI is missing after activation, fix packaging entry points or `pyproject.toml`, not `activate`.
- If deployment-scoped config is missing, fix `zday config init` or the explicit config/bootstrap path, not `activate`.
- Fallback behavior is an antipattern in this workspace. Do not add, preserve, or rely on inferred config paths, deprecated CLI aliases, alternate TLS discovery, generated substitute values, compatibility shims, or silent printer/rendering success when required state is missing. Missing config, certs, TapDB namespace, printer state, renderer dependency, or malformed input must fail hard with a clear error.

## Dependency Boundary

- `environment.yaml` is for Python bootstrap and non-Python/system packages only.
- Do not add Python libraries to `environment.yaml`, including `pip:` blocks or editable/dev dependency installs.
- All Python libraries belong in `pyproject.toml` under `project.dependencies`.
- Do not add or rely on extras groups for this repo.
- Do not add any secondary install set such as `.[dev]`, `.[test]`, or `requirements-dev.txt`.
- If a test or runtime import is missing, fix `pyproject.toml` or the explicit setup command, not `environment.yaml` or `activate`.

## PATH / CLI Availability

- Console scripts declared in `[project.scripts]` must be available from the active conda env after activation.
- If a script is missing from `PATH`, treat that as a packaging/editable-install bug.
- Do not repair `PATH` by adding shell aliases or repo-local wrapper hacks in `activate`.

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
- Move Python dependency management or config bootstrap logic back into `activate`.
