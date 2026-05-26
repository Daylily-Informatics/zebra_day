from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zebra_day import container_entry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_docker_runtime_files_use_foreground_uv_and_no_legacy_runtime() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (PROJECT_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER lsmc" in dockerfile
    assert "python\", \"-m\", \"zebra_day.container_entry" in dockerfile
    assert ":latest" not in dockerfile
    assert "conda" not in dockerfile.lower()
    assert "tmux" not in entrypoint
    assert "background" not in entrypoint
    assert "${ZEBRA_DAY_CONFIG_PATH:?ZEBRA_DAY_CONFIG_PATH is required}" in entrypoint


def test_container_entry_requires_absolute_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", "relative.yaml")

    with pytest.raises(RuntimeError, match="must be an absolute path"):
        container_entry._required_absolute_path("ZEBRA_DAY_CONFIG_PATH")


def test_container_entry_rejects_unknown_auth_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "zebra.yaml"
    config_path.write_text("service: {}\n", encoding="utf-8")
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ZEBRA_DAY_AUTH_MODE", "legacy")

    with pytest.raises(RuntimeError, match="must be none, cognito, or external_broker"):
        container_entry.main()


def test_container_entry_runs_foreground_http_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "zebra.yaml"
    config_path.write_text("service: {}\n", encoding="utf-8")
    monkeypatch.setenv("ZEBRA_DAY_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("ZEBRA_DAY_AUTH_MODE", "external_broker")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8118")

    with patch("zebra_day.container_entry.run_server") as run_server:
        container_entry.main()

    assert run_server.call_args.kwargs == {
        "host": "127.0.0.1",
        "port": 8118,
        "reload": False,
        "auth": "external_broker",
        "ssl_enabled": False,
    }
