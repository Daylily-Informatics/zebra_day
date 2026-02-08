# MODERNIZE.md - zebra_day Modernization Status

> **Status**: ALL PHASES COMPLETE as of 2.0.0, extended in 2.2.0

This document tracks the modernization of zebra_day from 0.5.0 to 2.2.0.

---

## Completed Modernization Summary

### Phase 0 - Hygiene + Guardrails
- [x] Removed duplicate dependencies
- [x] Moved dev-only deps to optional extras
- [x] Implemented structured logging
- [x] Created custom exceptions
- [x] Added comprehensive unit tests (102 tests passing, 62% coverage)

### Phase 1 - Packaging Modernization
- [x] Migrated to pyproject.toml (PEP 517/518)
- [x] Defined optional extras: dev, lint, docs, auth, all
- [x] Package builds correctly as wheel and sdist
- [x] PyPI-ready (twine check passes)

### Phase 2 - XDG Filesystem Safety
- [x] Implemented zebra_day/paths.py with XDG Base Directory support
- [x] Config: ~/.config/zebra_day/ (Linux + macOS; legacy macOS path supported for migration)
- [x] Data: ~/.local/share/zebra_day/ (Linux) or ~/Library/Application Support/zebra_day/ (macOS)
- [x] Logs: ~/.local/state/zebra_day/ (Linux) or ~/Library/Logs/zebra_day/ (macOS)
- [x] Replaced os.system() calls with pathlib + shutil

### Phase 3 - Web Stack Modernization
- [x] Migrated from CherryPy to FastAPI + Uvicorn
- [x] Implemented Jinja2 templates (13 modern templates)
- [x] Created versioned API (/api/v1/...)
- [x] Added OpenAPI documentation (/docs, /redoc)
- [x] Implemented optional Cognito authentication
- [x] Created modern UI with Ursa-inspired design system
- [x] Removed legacy UI (2.0.0) - modern UI only

### Phase 4 - Observability
- [x] Added health endpoints (/healthz, /readyz)
- [x] Implemented request logging middleware
- [x] Added structured logging with timestamps

### Phase 5 - CI/CD
- [x] GitHub Actions workflow with lint, test, build, publish jobs
- [x] Python version matrix (3.10, 3.11, 3.12, 3.13)
- [x] OS matrix (ubuntu-latest, macos-latest)
- [x] Ruff linting, Black formatting, mypy type checking
- [x] Automated PyPI publishing on release

### Phase 6 - v2.0.0 Breaking Changes
- [x] New printer configuration schema with nested printers object
- [x] Added printer_name, lab_location, manufacturer, notes, default_label_style fields
- [x] Added lab_name, available_locations, schema_version fields
- [x] HTTPS by default with mkcert support
- [x] Removed all legacy UI and bin scripts
- [x] Pure Python network scanner (replaced shell scripts)

### Bonus: Local ZPL Rendering
- [x] Replaced external Labelary API with local renderer
- [x] Implemented zebra_day/zpl_renderer.py using Pillow + zint-bindings

### Phase 7 - v2.2.0 Enhancements
- [x] Added `lsmc_euid` field (Lab Sample Management Container Enterprise Unique ID)
- [x] Separated Status (network reachability) from State (operational status)
- [x] Live printer status querying enabled by default
- [x] Added printer State field: Ready, Paused, Error, Offline, Unknown
- [x] Fixed `~HS` response parsing (pause flag at index 2)
- [x] Updated CLI `zday printer list --live` to show Status and State columns
- [x] Updated Web UI printers table with separate Status and State columns
- [x] Added 60-second caching for printer status queries
- [x] 152+ tests passing

### Phase 8 - cli-core-yo Migration + Simulator + ZPL-First Scanner
- [x] Migrated CLI from raw Typer to cli-core-yo foundation (`create_app(spec)` + plugin system)
- [x] Converted all command modules to `register()` plugin pattern (8 modules)
- [x] Standardized output: `console.print()` → `output.*` primitives (heading, success, warning, error, etc.)
- [x] Global `--json/-j` flag via RuntimeContext (replaced per-command `--json` flags)
- [x] Added mock Zebra printer simulator (`zday simulator start/stop/list`)
  - ZPL TCP server (port 9100) + HTTP status server (port 18080)
  - Configurable model, serial, firmware, and error conditions
- [x] Refactored network scanner to ZPL-first discovery (port 9100 default)
  - Optional HTTP fallback via `--scan-http-port`
  - Discovery method tracked in `notes` field: "zpl", "http(port)", "zpl+http(port)"
- [x] Fixed 27 pre-existing mypy errors (0 remaining)
- [x] ruff check + ruff format clean on all modified files
- [x] 334 tests passing across 13 test files

---

## Commands Reference

```bash
# Development
pytest -v                           # Run tests
pytest --cov=zebra_day              # Run tests with coverage
ruff check zebra_day tests          # Lint
ruff format --check zebra_day tests # Format check
mypy zebra_day                      # Type check

# CLI (global --json/-j flag available on all commands)
zday --help                         # Show all commands
zday info                           # Show config paths and status
zday bootstrap                      # First-time setup
zday gui start                      # Start web server (HTTPS by default)
zday gui start --no-https           # Start without HTTPS
zday gui stop                       # Stop web server
zday simulator start --foreground   # Mock printer for testing
zday printer scan --ip-stub 192.168.1  # ZPL-first scanner

# Build
python -m build                     # Build wheel and sdist
twine check dist/*                  # Verify package
```
