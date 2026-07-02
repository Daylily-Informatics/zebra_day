"""Container foreground entrypoint for zebra_day."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from zebra_day.web.app import run_server

AuthMode = Literal["none", "cognito", "external_broker"]


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _required_absolute_path(name: str) -> Path:
    path = Path(_required_env(name))
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be an absolute path")
    if not path.is_file():
        raise RuntimeError(f"{name} does not exist: {path}")
    return path


def main() -> None:
    _required_absolute_path("ZEBRA_DAY_CONFIG_PATH")
    auth_mode = _required_env("ZEBRA_DAY_AUTH_MODE")
    if auth_mode not in {"none", "cognito", "external_broker"}:
        raise RuntimeError("ZEBRA_DAY_AUTH_MODE must be none, cognito, or external_broker")
    run_server(
        host=_required_env("HOST"),
        port=int(_required_env("PORT")),
        reload=False,
        auth=cast(AuthMode, auth_mode),
        ssl_enabled=False,
    )


if __name__ == "__main__":
    main()
