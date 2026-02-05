# MODERNIZE.md - zebra_day Modernization Status

> **Status**: ALL PHASES COMPLETE as of 2.0.0

This document tracked the modernization of zebra_day from 0.5.0 to 2.0.0.

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

---

## Commands Reference

```bash
# Development
pytest -v                           # Run tests
pytest --cov=zebra_day              # Run tests with coverage
ruff check zebra_day tests          # Lint
ruff format --check zebra_day tests # Format check
mypy zebra_day                      # Type check

# CLI
zday --help                         # Show all commands
zday info                           # Show config paths and status
zday bootstrap                      # First-time setup
zday gui start                      # Start web server (HTTPS by default)
zday gui start --no-https           # Start without HTTPS
zday gui stop                       # Stop web server

# Build
python -m build                     # Build wheel and sdist
twine check dist/*                  # Verify package
```
