# zebra_day Dayhoff-Managed TapDB Startup Validation Plan

## Summary
Run the real `zebra_day` acceptance lane in two environments, `local` then `staging`, but first fix the one bootstrap flaw that would otherwise make the rollout fail: zebra_day’s deployment-scoped TapDB configs cannot be created by blindly copying `config/tapdb-config-zebra-day.yaml`, because TapDB requires `meta.database_name` to match the active namespace (`zebra-day-local`, `zebra-day-staging`).

The plan is therefore:
1. harden the Dayhoff/zebra_day bootstrap path so deployment-scoped zebra_day TapDB configs are initialized with the correct namespace metadata
2. run the Dayhoff-managed `local` launch twice: normal Cognito mode, then explicit `--no-auth`
3. run the Dayhoff-managed `staging` launch against Aurora
4. only after both pass, move on to Playwright, PRs, and release work

## Implementation Changes

### 1. Fix deployment-scoped zebra_day TapDB config bootstrap
- In the startup path used by both [host_deploy.py](/Users/jmajor/projects/dayhoff/scripts/host_deploy.py) and [local_runtime.py](/Users/jmajor/projects/dayhoff/scripts/local_runtime.py), stop treating zebra_day like Atlas/Kahlo for TapDB config initialization.
- Keep the existing path convention:
  - `~/.config/tapdb/zebra-day/zebra-day-local/tapdb-config.yaml`
  - `~/.config/tapdb/zebra-day/zebra-day-staging/tapdb-config.yaml`
- For zebra_day only, if that file is missing, initialize it with `tapdb config init` under the active namespace instead of copying [tapdb-config-zebra-day.yaml](/Users/jmajor/projects/daylily/zebra_day/config/tapdb-config-zebra-day.yaml) verbatim.
- Use the active Dayhoff payload values for the init step:
  - `client_id = zebra-day`
  - `database_name = zebra-day-<deployment>`
  - `env = dev`
  - `ui_port = 8118`
  - `db_port = 5544` for `local`
  - `db_port = 5432` for `staging`
- After init, align the env entry to zebra_day’s expected defaults:
  - local: `engine_type=local`, `database=zebra_day_dev`, `audit_log_euid_prefix=ZDY`, `support_email=support@lsmc.bio`
  - staging: `engine_type=aurora`, `database=zebra_day_prod`, `audit_log_euid_prefix=ZDY`, `support_email=support@lsmc.bio`, `cluster_identifier=zebra-day`, `region=us-west-2`, `iam_auth=true`, `ssl=true`
- Do not change the zebra_day runtime namespace contract. `database_name` stays deployment-scoped (`zebra-day-local`, `zebra-day-staging`).

### 2. Local Dayhoff-managed validation
- Create `~/.config/dayhoff/local_config.yaml` with:
  - `deploy_name=local`
  - `deploy_target=local`
  - `tapdb_locality=local`
  - default service roster including `zebra_day`
  - `profile=lsmc`
- Use the real Dayhoff CLI flow:
  1. `source /Users/jmajor/projects/dayhoff/activate --deploy-name local --region us-west-2`
  2. `dayhoff deploy build --region us-west-2 --deploy-name local --tapdb-locality local --deploy-target local`
  3. review/accept the generated config
  4. live launch with `--accept-existing-config --disable-dry-run --profile lsmc --global-admin-email <email>`
- Let Dayhoff own the actual zebra_day startup. Do not use an ad hoc standalone `zday gui start` for acceptance.
- Validate local in two runs:
  - Run A: default Cognito mode
  - Run B: explicit no-auth mode
- For Run B, add a local-only Dayhoff override in `overrides.services.zebra_day.start_commands` so zebra_day starts as `zday --no-auth gui start ...`. Do not test `--no-auth` by manually bypassing Dayhoff.

### 3. Staging Dayhoff-managed validation
- Create `~/.config/dayhoff/staging_config.yaml` with:
  - `deploy_name=staging`
  - `deploy_target=aws`
  - `tapdb_locality=aurora`
  - `profile=lsmc`
- Use the real Dayhoff AWS rollout flow:
  1. `source /Users/jmajor/projects/dayhoff/activate --deploy-name staging --region us-west-2`
  2. `dayhoff deploy build --region us-west-2 --deploy-name staging --tapdb-locality aurora --deploy-target aws`
  3. review/accept the generated config
  4. live rollout with `--accept-existing-config --disable-dry-run --profile lsmc --global-admin-email <email>`
- Before the zebra_day service start step on the target host, ensure the bootstrap logic from step 1 runs there too, so the host receives a valid `zebra-day-staging` TapDB config instead of a copied base template.
- For staging, keep normal auth enabled. Do not run staging in `--no-auth`.
- Use the existing Aurora cluster identifier `zebra-day` in `us-west-2`; bootstrap should reuse it if present and create it only if absent.

## Operational Interfaces
- No user-facing API changes are required for this tranche.
- The operational contract changes are:
  - zebra_day deployment-scoped TapDB configs are initialized, not copied
  - Dayhoff remains the owner of the live startup path for both `local` and `staging`
  - the local `--no-auth` proof is exercised through Dayhoff `start_commands`, not a side launch
- Required operator inputs before execution:
  - one global admin email for new-deployment bootstrap
  - AWS profile `lsmc`
  - valid local Cognito/daycog prerequisites already used by Dayhoff auth preparation

## Test Plan
- Add bootstrap regression tests in Dayhoff:
  - zebra_day local script initializes `zebra-day-local` config metadata correctly
  - zebra_day staging host script initializes `zebra-day-staging` config metadata correctly
  - no generated zebra_day startup script relies on raw template-copy metadata
- Add zebra_day-side regression coverage:
  - deployment-scoped TapDB config expectations still resolve to `zebra-day-<deployment>`
  - startup fails when neither a valid config nor bootstrap init step is available
- Local acceptance must pass:
  - `https://localhost:8118/healthz`
  - `https://localhost:8118/readyz`
  - `https://localhost:8118/obs_services`
  - `https://localhost:8118/api/v1/labs`
  - `https://localhost:8118/api/v1/templates`
  - authenticated `/`
  - authenticated `/admin`
  - one print-resolution API path
  - second pass with `--no-auth` where `/` and `/admin` are anonymously reachable
- Staging acceptance must pass:
  - Dayhoff rollout completes without zebra_day bootstrap failure
  - `/healthz`, `/readyz`, `/obs_services`, `/api/v1/labs`, `/api/v1/templates`
  - Cognito login/logout callback behavior
  - `/admin` for admin user
  - service-token access with `Bearer INTERNAL_API_KEY`

## Assumptions
- `local` and `staging` are the exact Dayhoff deployment names to use for this tranche.
- `tapdb.env` remains `dev` for both environments because that is how Dayhoff now seeds the explicit service TapDB contract.
- The Aurora target for zebra_day staging is the shared service cluster identifier `zebra-day` in `us-west-2`.
- A global admin email is required because both `local` and `staging` are treated as brand-new Dayhoff deployments unless the AWS stack already exists.
- Live Playwright/Cognito E2E, cross-repo PRs, tagging, and publish work remain blocked until this startup-validation tranche passes.
