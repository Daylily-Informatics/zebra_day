# zebra_day UI Guide

## Web Surface

The modern GUI is served by the same FastAPI application that exposes the JSON API.

| Route | Purpose |
|---|---|
| `/` | Dashboard and service entrypoint |
| `/printers` | Printer fleet overview and discovery |
| `/templates` | Shared TapDB template management |
| `/print` | Resolve, preview, and submit print jobs |
| `/config` | Deployment, TapDB, and runtime configuration |
| `/admin` | Auth, observability, and operator/admin runtime status |
| `/docs` | Swagger UI |
| `/redoc` | Read-only API reference |

## Auth

Default mode is Cognito session auth backed by the active `daycog` context.

- HTML routes redirect to `/auth/login` when auth is enabled
- machine clients may use `Bearer INTERNAL_API_KEY`
- `zday --no-auth ...` or `zday gui start --no-auth` disables auth for that server process

The dedicated `/auth/error` page is used for failed callbacks and authorization failures. It does not reuse the dashboard shell.

## Printer Fleet Page

The fleet page reads curated printers from TapDB and lets operators run network discovery. Discovery calls the JSON API and records observations plus draft printer candidates in TapDB.

## Templates Page

The templates page reads and writes shared TapDB template records through the JSON API. It also shows label-profile bindings so operators can see which profile resolves to which template.

## Print Page

The print page uses the JSON API for three operations:

- resolve a print request and inspect the final printer/template choice
- render a PNG preview
- submit a server-side print job

## Observability

The admin page links to the structured observability contract:

- `/health`
- `/obs_services`
- `/api_health`
- `/endpoint_health`
- `/db_health`
- `/my_health`
- `/auth_health`
