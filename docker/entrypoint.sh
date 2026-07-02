#!/usr/bin/env sh
set -eu

: "${LSMC_SERVICE_NAME:?LSMC_SERVICE_NAME is required}"
: "${LSMC_ENV:?LSMC_ENV is required}"
: "${LSMC_RUNTIME_CLASS:?LSMC_RUNTIME_CLASS is required}"
: "${ZEBRA_DAY_CONFIG_PATH:?ZEBRA_DAY_CONFIG_PATH is required}"
: "${ZEBRA_DAY_AUTH_MODE:?ZEBRA_DAY_AUTH_MODE is required}"
: "${HOST:?HOST is required}"
: "${PORT:?PORT is required}"
: "${OTEL_EXPORTER_OTLP_ENDPOINT:?OTEL_EXPORTER_OTLP_ENDPOINT is required}"

export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-$LSMC_SERVICE_NAME}"
export OTEL_RESOURCE_ATTRIBUTES="service.name=${OTEL_SERVICE_NAME},deployment.environment=${LSMC_ENV},service.version=${LSMC_RELEASE_SHA:-unknown}"
export LOG_FORMAT="${LOG_FORMAT:-json}"

exec "$@"
