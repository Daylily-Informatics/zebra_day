# Zebra Day Access Logging And AI-Agent Read Access Gap

Created: 2026-06-04T11:07:00Z

## Status

SUPERSEDED for local `jem-dev` source by commit `b286b77` and release tag
`7.0.1`. Zebra Day now has the local source pieces for Kahlo-issued read-only
AI-agent validation, broker-backed theme preferences, and common access logging.

Remaining acceptance moved to the Dayhoff final beta ledger:
`/Users/jmajor/projects/mega_dayhoff/dayhoff/docs/plans/20260606T080000Z_final_beta_release_consolidation_ledger.md`.
That acceptance requires the future `jemdev` deployment and must not use
production `day` services.

## Required Contract

- Validate Kahlo-issued AI-agent bearer tokens against an explicit Dayhoff-generated allowlist.
- Accept only read-only endpoint IDs approved for Zebra Day lab, label, template, and printer-status search/detail APIs.
- Record every endpoint access with request ID, correlation ID, route template, status, duration, client IP, auth mode, human user, service ID, AI-agent ID, authorizing human, token ID prefix/hash, scopes, and denial reason.
- Never log raw label contents, printer credentials, bearer tokens, cookies, or raw request/response bodies.

## Historical Gap

At creation time, Zebra Day had historical structured/request logging notes, but
source did not prove the new uniform all-endpoint access-log schema with
AI-agent provenance or Kahlo-issued AI-agent token validation. That is no longer
the current local `jem-dev` source state.

## Acceptance

- Focused tests prove allowed AI-agent tokens can read only approved Zebra Day search/detail endpoints.
- Printer action, label mutation, admin, and non-allowlisted routes reject AI-agent tokens.
- Access-log tests prove actor/IP/request/token fields and redaction.
