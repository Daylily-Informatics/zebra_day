# zebra_day 3.0 Major Refactor

Implementation handoff for the approved `zebra_day` major release.

## Summary

This release turns `zebra_day` into a deployment-scoped, TapDB-backed, first-level
service and library.

- Runtime activation moves to Atlas-style `source ./activate`.
- Local flat files stop being the runtime source of truth for printer fleet state.
- TapDB becomes the primary authority for printers, label profiles, templates, and
  print jobs.
- Default web auth becomes Cognito session auth via `daycog`; `--no-auth` remains
  the only explicit compatibility bypass.
- The web UI keeps FastAPI + Jinja2, but pages become thin shells backed by JSON
  APIs and Kahlo-compatible observability.
- `zebra_day` is promoted into Dayhoff’s static service catalog now, and Bloom
  integrates through a stable zebra_day facade instead of `print_mgr.zpl()`.

## Decisions

- Release target: `3.0.0`
- TapDB mode: primary authority
- Printer metadata model: dual authority, but TapDB wins conflicts
- Dayhoff posture: promote `zebra_day` to a first-level service now
- Auth default: Cognito
- Compatibility carve-out: `--no-auth` only
- Legacy support: no dual-read or dual-write runtime path

## Agent Workstreams

### Agent 1: Runtime, Config, And CLI Foundation

Ownership:
- `activate`
- `zebra_day/cli/`
- new typed settings/config loader
- deployment-scoped XDG path handling

Deliverables:
- Replace `zday_activate` with Atlas-style `source ./activate`.
- Derive deployment code from
  `ZEBRA_DAY_DEPLOYMENT_CODE|DEPLOYMENT_CODE|LSMC_DEPLOYMENT_CODE`.
- Canonical config path becomes
  `~/.config/zebra-day-<deployment>/zebra-day-config-<deployment>.yaml`.
- Move the CLI to `CliSpec + EnvSpec`, generated config template bytes, built-in
  config group commands, and extra `config status` / `config routes` helpers.
- Remove local fleet and DynamoDB backends as supported runtime authorities.
- Add CLI preflight for TapDB config, daycog context, callback/logout validation,
  and HTTPS readiness before server start.

### Agent 2: TapDB Domain Model And Repository Layer

Ownership:
- TapDB adapter layer in `zebra_day`
- repo JSON packs under `config/tapdb_templates/`
- stable repository/service interfaces used by CLI, API, and GUI

Deliverables:
- Adopt strict TapDB namespace context:
  - `TAPDB_CLIENT_ID=zebra-day`
  - `TAPDB_DATABASE_NAME=zebra-day-<deployment>`
  - `TAPDB_ENV`
- Resolve TapDB config from
  `~/.config/tapdb/<client>/<database>/tapdb-config.yaml` unless explicitly
  overridden by `TAPDB_CONFIG_PATH`.
- Define fixed object types for:
  - `printer`
  - `label_profile`
  - `label_template`
  - `printer_observation`
  - `metadata_drift`
  - `print_job`
- Seed template definitions from repo JSON packs; runtime records are stored as
  TapDB instances, not as flat files or dynamic template definitions.
- Keep `daylily-tapdb` changes minimal and only for missing generic helpers, docs,
  or tests.

### Agent 3: Discovery, Metadata Sync, And Print Routing

Ownership:
- scanner and printer-protocol logic
- metadata reconciliation
- print default resolution

Deliverables:
- Discovery reads hardware facts via ZPL first:
  - `~HI`
  - `~HQSN`
  - `~HS`
  - optional HTTP supplement when configured
- Store observations separately from curated printer records.
- Enforce dual-authority rule:
  - TapDB is authoritative for curated fields
  - printer-sourced data may fill blanks
  - printer-sourced data may refresh immutable device fingerprint fields
  - printer-sourced data may open drift/adoption records
  - printer-sourced data never silently overwrites curated TapDB defaults,
    location, or naming
- Do not jam JSON into `printer_name` or other human-facing fields.
- If on-device metadata is supported, use a dedicated reserved device-manifest
  channel only.
- Unknown scanned printers auto-create draft candidate records with observed
  facts; reserved device-manifest values are attached as suggestions, not truth.
- Print routing resolves defaults in this order:
  1. explicit request override
  2. TapDB label-profile default
  3. verified device-manifest default
  4. hard fail if no valid profile remains

### Agent 4: Web App, Auth, And Observability

Ownership:
- `zebra_day/web/`
- page shells and JSON APIs
- auth flow, docs gating, and observability contract

Deliverables:
- Keep FastAPI as the parent app and Jinja2 as the shell layer.
- Make page routes thin shells only; live data comes from same-origin JSON APIs.
- Default auth mode is Cognito session auth backed by daycog context and
  Atlas/Kahlo-style callback/logout validation.
- `--no-auth` is the only compatibility bypass.
- Normal auth rules:
  - page routes require session auth
  - JSON APIs accept session or `Bearer INTERNAL_API_KEY`
  - only `/healthz` and `/readyz` remain public
- Expose Kahlo-compatible observability endpoints:
  - `/healthz`
  - `/readyz`
  - `/health`
  - `/obs_services`
  - `/api_health`
  - `/endpoint_health`
  - `/db_health`
  - `/my_health`
  - `/auth_health`
- Every structured payload uses the Kahlo frame:
  - `contract_version`
  - `service`
  - `environment`
  - `instance_id`
  - `observed_at`
  - `status`
  - `request_id`
  - `correlation_id`
  - `build`
  - `projection` where applicable
- Middleware injects request/correlation IDs, returns `X-Request-ID` and
  `X-Correlation-ID`, and records route templates rather than concrete paths.
- Gate Swagger, ReDoc, and OpenAPI like Atlas/Kahlo. No default public docs.

### Agent 5: Downstream Integration And Dayhoff Promotion

Ownership:
- coordinated PRs in `dayhoff`
- coordinated PRs in `bloom`
- any required touchpoints in `daylily-cognito` or `daylily-tapdb`

Deliverables:
- Dayhoff:
  - add `zebra_day` as a first-level private service on port `8118`
  - set `cli: zday`
  - set `activate_path: activate`
  - declare TapDB bootstrap dependency
  - add directory metadata and pin the major release
- Kahlo:
  - include zebra_day in directory and fleet views as a static first-level
    service
  - consume zebra_day’s observability contract directly
- Bloom:
  - remove direct reliance on `print_mgr.zpl()`
  - remove direct reliance on `.printers` and flat-file assumptions
  - integrate through the stable zebra_day facade and/or protected APIs
- daycog:
  - use app-client name `zebra-day`
  - keep pool/app/client lifecycle in `daycog`
  - zebra_day only binds, imports, and validates the resolved auth contract

### Agent 6: Tests, Docs, And Release Hardening

Ownership:
- route coverage
- contract tests
- README/docs refresh
- release cleanup

Deliverables:
- Add route-surface audit so every non-health API and page route has at least
  one direct request test.
- Add observability schema tests against checked-in JSON Schemas.
- Add auth-mode matrix tests:
  - Cognito/session
  - service token
  - `--no-auth`
- Update Bloom-facing docs and remove deprecated startup guidance such as
  `zday_start`, flat-file editing, and package-template mutation.
- Cut the release as a major version with deprecated internals removed from
  supported integration guidance.

## Public Interface Changes

### Runtime And Config Contract

- `source ./activate`
- deployment-scoped YAML settings at
  `~/.config/zebra-day-<deployment>/zebra-day-config-<deployment>.yaml`
- repo-owned JSON TapDB packs under `config/tapdb_templates/`
- TapDB namespace via `TAPDB_CLIENT_ID`, `TAPDB_DATABASE_NAME`, and `TAPDB_ENV`

### Supported Python Facade

- `ZebraDaySettings.from_context(deployment=None)`
- `ZebraDayClient(settings)`

Supported methods:
- `list_labs()`
- `list_printers(lab)`
- `get_printer(printer_id)`
- `discover_printers(...)`
- `sync_printer_metadata(...)`
- `update_printer_metadata(...)`
- `list_templates()`
- `render_label(...)`
- `print_label(...)`

### Supported Auth And Admin CLI

- `zday cognito bind`
- `zday cognito import`
- `zday cognito status`
- `zday cognito validate`
- `zday gui start` defaults to Cognito
- `--no-auth` remains explicit compatibility mode

### Unsupported Going Forward

- direct client reliance on `print_mgr.zpl()`
- direct client reliance on `.printers`
- direct client reliance on `.printers_filename`
- flat-file fleet state as runtime truth
- DynamoDB/S3 fleet backend as the primary runtime authority

## Test Plan

### zebra_day

- settings-loader tests for deployment-scoped YAML and TapDB namespace resolution
- repository tests for printer/template/profile CRUD, observation ingest, drift
  creation, and conflict precedence
- discovery tests for ZPL parsing, HTTP supplement, unknown-printer draft
  creation, and device-manifest parsing
- direct-request tests for every page route and every API route
- observability schema tests and route-template audit tests
- auth tests for session flow, service-token access, docs gating, and `--no-auth`

### dayhoff

- service-catalog and directory tests proving zebra_day is first-level and
  visible in Kahlo
- fleet polling and expectation tests against zebra_day `obs_services`

### bloom

- client integration tests against the stable zebra_day facade
- regression tests for printer selection, default-label resolution, preview, and
  print calls

### Verification Environments

- simulator-backed end-to-end run
- at least one physical-printer validation pass for scan, metadata sync, preview,
  and print-default behavior

## Assumptions

- TapDB is the primary runtime authority.
- Local files remain only for deployment, runtime, and bootstrap configuration.
- Printer metadata is dual-authority, but TapDB wins conflicts.
- `zebra_day` is promoted to a first-level Dayhoff service now.
- Default auth is Cognito.
- `--no-auth` is the only planned compatibility bypass.
- No legacy dual-read or dual-write runtime path is included.
- Legacy YAML, JSON, and DynamoDB fleet data are out of scope unless a separate
  import task is explicitly approved.
