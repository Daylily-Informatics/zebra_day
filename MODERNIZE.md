## MODERNIZE.md — zebra_day modernization plan using git tag 0.5.0

### What I reviewed (repo facts)
- Python package with `setup.py` (setuptools) and `requirements.txt`.
- Runtime deps currently include `cherrypy`, `requests`, `pytz`, `ipython`, `pytest`, `yaml_config_day`.
- Web UI is CherryPy (`zebra_day/bin/zserve.py`) with hand-built HTML strings.
- Core logic in `zebra_day/print_mgr.py` and `zebra_day/cmd_mgr.py`.
- Package writes config/logs/templates inside the installed package tree via `importlib.resources.files('zebra_day')` + `os.system(...)`.
- Network discovery + several operations use shelling out (`os.system`, `os.popen`, `curl`, `arp`).
- Tests exist but are minimal; `tests/test_web_server.py` is a stub.
- No `.augment/` project instruction directory found.

---

## Assumptions
- Keep `zday_start` / `zday_quickstart` CLI behavior stable (or provide a compatibility shim).
- Keep “works on macOS + Ubuntu” as the baseline.
- Avoid adding heavyweight dependencies unless they clearly reduce operational risk.

## Trade-offs
- **Stability vs. modernization speed**: largest risk is changing persistence paths and the web stack; phase those changes.
- **Fewer deps vs. better ergonomics**: e.g., IP detection/config dirs can be stdlib-only but less robust.
- **Local/offline vs. cloud conveniences**: Labelary PNG rendering is an external HTTP dependency; replacing it is work.

---

## Recommended path (phased, lowest-risk first)

### Phase 0 — “Hygiene + guardrails” (1–2 days)
1. **Dependency hygiene**
   - Remove duplicates in `requirements.txt` (currently `pytest` appears twice).
   - Move dev-only deps out of runtime install:
     - `pytest`, `ipython` should not be in `install_requires`.
2. **Logging & error surfaces**
   - Replace `print(..., file=sys.stderr)` with `logging` (structured levels, timestamps).
   - Convert generic `Exception(...)` to specific exceptions (connection errors, config errors).
3. **Test baseline**
   - Add unit tests around:
     - `formulate_zpl()` templating behavior
     - socket send logic (mock socket)
     - printer-config JSON load/save roundtrip

### Phase 1 — Packaging modernization (0.5–1.5 days)
1. **Move to `pyproject.toml` (PEP 517/518)**
   - Keep setuptools backend initially (low risk).
   - Define metadata, classifiers, `requires-python >=3.10`.
   - Declare optional extras: `dev`, `ui`, `docs`.
2. **Make packaging deterministic**
   - Use `MANIFEST.in` and/or modern `setuptools` config for including `etc/`, `static/`, `bin/` data.
   - Ensure sdist/wheel include required templates/static files.
3. **Pin policy**
   - Prefer `>=` ranges for libraries unless breakage is known; keep pins where required.
   - Keep a separate lock for dev (if you adopt `uv`/`pip-tools`/Poetry later).

### Phase 2 — Correct persistence + filesystem safety (2–4 days)
This is the highest immediate reliability win.
1. **Stop writing into site-packages**
   - Move mutable state to user/system locations:
     - printer config JSON
     - generated PNGs
     - logs
     - temp label drafts
   - Use `XDG_CONFIG_HOME`/`~/.config` and `XDG_STATE_HOME`/`~/.local/state` (or platform equivalents).
2. **Replace shell-based file operations**
   - Replace `os.system("mkdir -p ...")`, `cp`, `echo` with `pathlib` + `shutil`.
   - Benefit: cross-platform correctness + avoids shell injection.
3. **Config migration strategy**
   - On first run, if legacy config exists under package `etc/`, copy it to the new config dir.
   - Print a clear one-time message explaining the new location.

### Phase 3 — Web stack modernization (optional, medium risk) (3–10 days)
CherryPy works, but modern Python web tooling is centered around ASGI.
1. **Split UI vs API**
   - Keep existing endpoints, but introduce a versioned JSON API surface (`/api/v1/...`).
2. **Move to FastAPI + Jinja2 (recommended)**
   - FastAPI for API + OpenAPI docs.
   - Jinja2 templates instead of string-concatenated HTML.
   - Run via `uvicorn`.
   - Do not keep cherrypy as a compatibility mode.
3. **Security basics**
   - Replace current “envcheck + sleep” gate with:
     - optional auth token, or
     - bind to localhost by default, with an explicit `--host 0.0.0.0` flag.

### Phase 4 — Observability + operability (1–3 days)
- Add structured request logging (client IP, lab/printer/template, outcome).
- Add health endpoints (`/healthz`, `/readyz`).
- Add rate limiting or simple concurrency controls for print endpoints.

### Phase 5 — Release + CI upgrades (1–2 days)
- CI: run unit tests + lint + typecheck.
- Add formatting/linting (Black/Ruff) and optional typing (mypy/pyright).
- Automate releases (tag-driven) and publish artifacts.

---

## Concrete modernization backlog (ordered)
1. Move runtime state out of package dir (config/logs/files/tmps).
2. Convert shelling out to Python stdlib (pathlib/shutil/subprocess).
3. Separate runtime vs dev dependencies.
4. Add meaningful unit tests with network calls mocked.
5. Introduce a real web API contract (versioned, JSON).
6. Execute ASGI migration (FastAPI) and template-driven HTML. Improve GUI interactions.

## “Reproduce this” commands (targets)
- Unit tests: `pytest -q`
- Lint (if added): `ruff check .`
- Format (if added): `black .`
- Typecheck (if added): `mypy zebra_day`

## Finally, Plan For
- Replacing labelary PNG rendering is an external HTTP dependency; replacing it is work.