"""zebra_day web application module."""

from __future__ import annotations

from typing import Any

__all__ = ["create_app"]


def create_app(*args: Any, **kwargs: Any) -> Any:
    from zebra_day.web.app import create_app as _create_app

    return _create_app(*args, **kwargs)
