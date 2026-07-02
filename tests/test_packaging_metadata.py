from __future__ import annotations

import tomllib
from pathlib import Path


def _tapdb_version(dependencies: list[str]) -> str:
    for dependency in dependencies:
        if dependency.startswith("daylily-tapdb=="):
            return dependency.split("==", 1)[1]
        if dependency.startswith("daylily-tapdb @ ") and "@" in dependency:
            return dependency.rsplit("@", 1)[1].strip()
    raise AssertionError("daylily-tapdb dependency is missing")


def test_pyproject_pins_release_train_dependencies() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    dependencies = data["project"]["dependencies"]
    tapdb_spec = next(dep for dep in dependencies if dep.startswith("daylily-tapdb"))

    assert "cli-core-yo==2.1.1" in dependencies
    assert "daylily-auth-cognito==2.1.5" in dependencies
    assert (
        tapdb_spec
        == "daylily-tapdb @ git+https://github.com/Daylily-Informatics/daylily-tapdb.git@9.0.9"
    )
    assert all("daylily-cognito" not in dependency for dependency in dependencies)
