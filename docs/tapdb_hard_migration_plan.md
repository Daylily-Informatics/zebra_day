# zebra_day TapDB Hard Migration Plan Replacement

## Summary

This refactor remains a breaking TapDB-only cut for shared fleet state: no local-file, DynamoDB, S3-backup, or in-memory datastore paths remain in supported runtime code. The main change from the prior hard-cut plan is that auth keeps an explicit global `--no-auth` runtime override, and the Python library split becomes dual-mode by responsibility:

- the zebra_day service and admin/CLI runtime use direct TapDB via `ZebraDayClient`
- downstream Python apps use a separate API-backed client to fetch shared printer/template/profile state from a specified zebra_day service and can still send print requests to printers through library code

Default posture is still Cognito auth and TapDB-backed service ownership of shared state. `--no-auth` is the only retained compatibility override.

## Multiagent Workstreams

### Agent 1: TapDB Hard Cut And Runtime Cleanup

Ownership:
- storage/runtime architecture
- delete set
- server-side Python client

Deliverables:
- Delete the legacy storage layer and all related runtime selection logic:
  - `backends/local.py`
  - `backends/dynamo.py`
  - `backends/memory.py`
  - `backends/__init__.py`
  - `ZEBRA_DAY_CONFIG_BACKEND`
- Remove all TapDB failure fallbacks, especially `InMemoryFleetRepository` and any silent fallback-to-memory behavior.
- Remove legacy engine/config bridges:
  - `_legacy_config()`
  - `_legacy_engine()`
  - `PrinterRecord.to_legacy_dict()`
  - package-root shim helpers that exist only to preserve old result shapes
- Keep `ZebraDayClient` as the server/admin client for direct TapDB use only.
- Make `ZebraDayClient` fail fast if TapDB config, TapDB connectivity, or required TapDB dependencies are missing.
- Keep checked-in `.zpl` assets only as bootstrap seed content for TapDB, never as runtime state.

### Agent 2: Printer Protocol And Library Split

Ownership:
- printer transport
- discovery/render/print logic
- downstream Python API client

Deliverables:
- Remove `print_mgr.zpl()` as a supported runtime engine.
- Extract raw printer/render helpers into internal protocol modules that do not own config storage.
- Rebuild server-side discovery, render, and print flows so they resolve state from TapDB directly and write observations/print jobs back to TapDB directly.
- Add a new downstream API-backed client, `ZebraDayApiClient`, for apps like Bloom and other Python consumers.
- `ZebraDayApiClient` must fetch shared state from a configured zebra_day HTTP API, not from TapDB.
- `ZebraDayApiClient.print_label(...)` must support direct printer delivery after remote resolution of printer/template/profile/defaults.
- `ZebraDayApiClient.submit_print_job(...)` must support optional server-side print submission through the zebra_day API.
- `ZebraDayClient` remains the only direct-TapDB client; downstream apps should not talk to TapDB directly.

### Agent 3: Atlas-Style Activation And CLI Rebuild

Ownership:
- `activate`
- `zday` command surface
- deployment/runtime guardrails

Deliverables:
- Replace activation with Atlas-style `source ./activate <deploy-name>`.
- Activation must require exactly one deploy name, sanitize it, export deployment vars, and activate or create a conda env named `ZEBRA_DAY-<deploy-name>`.
- Deployment-scoped config lives under `~/.config/zebra_day/...-<deploy-name>` and stores service/auth/runtime settings only.
- Rebuild `zday` around Atlas-style `CliSpec + EnvSpec + ConfigSpec + XdgSpec`.
- Remove legacy CLI groups tied to old stores or file editing:
  - `zday dynamo`
  - YAML/JSON fleet-editing commands
  - local template file-management commands as runtime authority
- Add Atlas-style passthrough groups:
  - `zday tapdb ...`
  - `zday cognito ...`
- Add zebra_day-native management groups:
  - `zday gui ...`
  - `zday logs ...`
  - `zday printers ...`
  - `zday users ...`
- Add a root/global `--no-auth` option on the CLI runtime so `zday --no-auth ...` and `zday gui start --no-auth` disable web/API auth for that invocation.
- Keep default auth mode as Cognito in config and startup validation; `--no-auth` is an explicit runtime override, not the default.

### Agent 4: Web/API/UI Contract Rewrite

Ownership:
- FastAPI app
- JSON API contract
- Jinja UI
- auth/runtime behavior

Deliverables:
- Make the FastAPI app TapDB-backed only. App startup must fail if TapDB is unavailable.
- Remove all web/runtime dependence on `app.state.zp`, `_backend`, local template scans, backend switching, import-to-dynamo flows, and legacy-config listings.
- Keep FastAPI + Jinja, but make every page/API route operate on TapDB-native records only.
- Preserve a stable API contract specifically for the new downstream `ZebraDayApiClient`.
- Supported remote-state endpoints must include:
  - labs
  - printers
  - templates
  - label profiles
  - render/resolve helpers
  - server-side print submission
- Auth rules:
  - default service mode uses Cognito
  - machine clients may use `Bearer INTERNAL_API_KEY`
  - global `--no-auth` disables route auth for that server instance
- UI/admin pages must expose deployment, TapDB namespace, auth mode, health, logs, printer fleet, templates, and user/admin operations without any multi-backend UI.

### Agent 5: Tests, Docs, And Release Contract

Ownership:
- test rewrite
- doc rewrite
- breaking-change contract

Deliverables:
- Delete or rewrite all tests that assume local YAML/JSON state, DynamoDB/S3, backend switching, legacy config migration, or in-memory repository fallback.
- Replace them with TapDB-backed fixtures and API-backed client tests.
- Add a dedicated test matrix for auth modes:
  - Cognito enabled
  - service token / `INTERNAL_API_KEY`
  - global `--no-auth`
- Add dedicated tests for the new library split:
  - `ZebraDayClient` direct-TapDB behavior
  - `ZebraDayApiClient` remote fetch + local direct-print behavior
  - `ZebraDayApiClient.submit_print_job(...)` server-submitted behavior
- Rewrite docs so this file is the canonical hard-migration spec reflecting:
  - TapDB-only shared state
  - Atlas-style activation
  - global `--no-auth`
  - dual Python client model
  - removal of old local/Dynamo runtime paths
- Add explicit breaking-release notes listing removed commands, env vars, modules, and deprecated Python entrypoints.

## Public Interfaces

Supported after the cut:
- `source ./activate <deploy-name>`
- `ZebraDaySettings.from_context(deployment=None)`
- `ZebraDayClient(settings)` for direct TapDB service/admin usage
- `ZebraDayApiClient(base_url, api_key=None, verify_ssl=True)` for downstream apps that fetch shared state from a zebra_day API
- `zday --no-auth ...` as a global runtime auth override
- `zday` command groups for GUI, logs, printers, users, TapDB passthrough, and Cognito passthrough

Removed after the cut:
- `print_mgr.zpl()` as a supported engine
- package-root legacy helper surface that returns YAML-era printer dicts
- `zday_activate`
- `zday_start`
- `zday_quickstart`
- `zday dynamo`
- `ZEBRA_DAY_CONFIG_BACKEND`
- local YAML/JSON fleet config as runtime state
- DynamoDB/S3 runtime support
- in-memory datastore/runtime fallback
- sibling-package fallback CLIs or legacy-env auth bootstrap

## Test Plan

- Activation tests:
  - `source ./activate <deploy-name>` requires exactly one deploy name
  - invalid deploy names hard fail
  - active env name matches `ZEBRA_DAY-<deploy-name>`
  - deployment-scoped config and TapDB vars resolve correctly
- Direct TapDB runtime tests:
  - `ZebraDayClient` fails fast when TapDB is missing
  - no code path falls back to memory, local files, or Dynamo
  - discovery/render/print work without `print_mgr.zpl()`
- Remote client tests:
  - `ZebraDayApiClient` lists labs/printers/templates from API
  - template/profile/default resolution from API is correct
  - direct printer send after remote resolution works
  - server-side `submit_print_job(...)` works
- Auth tests:
  - Cognito mode protects routes and API as expected
  - `INTERNAL_API_KEY` works for machine clients
  - global `--no-auth` removes auth requirements for that process
- Regression guards:
  - no imports remain from `zebra_day.backends.*`
  - no supported runtime code depends on `print_mgr.zpl()`
  - no docs or CLI help mention local/Dynamo operational modes

## Assumptions And Defaults

- No offline migrator is shipped. Old local/Dynamo data are out of scope for this cut.
- Shared fleet/template/profile state lives only in TapDB through the zebra_day service.
- Downstream Python apps should use `ZebraDayApiClient`, not direct TapDB access.
- `ZebraDayApiClient.print_label(...)` defaults to direct printer delivery after remote resolution; server-side delivery is explicit through `submit_print_job(...)`.
- Default auth mode remains Cognito. `--no-auth` is retained as the only explicit runtime bypass.
