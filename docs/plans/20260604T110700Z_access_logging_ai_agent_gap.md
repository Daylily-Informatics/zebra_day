# Zebra Day Access Logging And AI-Agent Read Access Gap

Created: 2026-06-04T11:07:00Z

## Status

Zebra Day needs a follow-up implementation pass before Kahlo-issued AI-agent tokens can safely read Zebra Day search/detail APIs directly.

## Required Contract

- Validate Kahlo-issued AI-agent bearer tokens against an explicit Dayhoff-generated allowlist.
- Accept only read-only endpoint IDs approved for Zebra Day lab, label, template, and printer-status search/detail APIs.
- Record every endpoint access with request ID, correlation ID, route template, status, duration, client IP, auth mode, human user, service ID, AI-agent ID, authorizing human, token ID prefix/hash, scopes, and denial reason.
- Never log raw label contents, printer credentials, bearer tokens, cookies, or raw request/response bodies.

## Current Gap

Zebra Day has historical structured/request logging notes, but current source does not prove the new uniform all-endpoint access-log schema with AI-agent provenance or Kahlo-issued AI-agent token validation.

## Acceptance

- Focused tests prove allowed AI-agent tokens can read only approved Zebra Day search/detail endpoints.
- Printer action, label mutation, admin, and non-allowlisted routes reject AI-agent tokens.
- Access-log tests prove actor/IP/request/token fields and redaction.
