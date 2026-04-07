from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_pins_release_train_dependencies() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    dependencies = data["project"]["dependencies"]

    assert "cli-core-yo==2.0.0" in dependencies
    assert "daylily-auth-cognito==2.0.2" in dependencies
    assert "daylily-tapdb==5.0.4" in dependencies
    assert all("daylily-cognito" not in dependency for dependency in dependencies)
