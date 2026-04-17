from __future__ import annotations

import json

from cli_core_yo.runtime_checks import evaluate_prereq
from typer.testing import CliRunner

from zebra_day.cli import app, spec

runner = CliRunner()


def _runtime_prereq(key: str):
    assert spec.runtime is not None
    for prereq in spec.runtime.prereqs:
        if prereq.key == key:
            return prereq
    raise AssertionError(f"missing prereq {key}")


def test_cli_spec_uses_platform_v2_runtime_and_context() -> None:
    assert spec.policy.profile == "platform-v2"
    assert spec.runtime is not None
    assert spec.runtime.default_backend == "zebra-day-conda"
    assert spec.runtime.allow_skip_check is False
    assert spec.context is not None
    assert [option.name for option in spec.context.options] == ["no_auth"]
    assert {prereq.key for prereq in spec.runtime.prereqs} == {
        "zebra-day-conda-active-env",
        "zebra-day-conda-env-name",
        "zebra-day-daylily-tapdb",
        "zebra-day-daylily-auth-cognito",
    }


def test_cli_runtime_requires_active_conda_env() -> None:
    result = evaluate_prereq(
        _runtime_prereq("zebra-day-conda-active-env"),
        env={"CONDA_DEFAULT_ENV": ""},
    )

    assert result.status == "fail"
    assert "active deployment-scoped conda environment" in result.summary


def test_cli_runtime_requires_conda_env_name_prefix() -> None:
    result = evaluate_prereq(
        _runtime_prereq("zebra-day-conda-env-name"),
        env={"CONDA_DEFAULT_ENV": "ZEBRA_DAY-other"},
    )

    assert result.status == "pass"


def test_cli_runtime_rejects_non_zebra_conda_env_name() -> None:
    result = evaluate_prereq(
        _runtime_prereq("zebra-day-conda-env-name"),
        env={"CONDA_DEFAULT_ENV": "other"},
    )

    assert result.status == "fail"
    assert "CONDA_DEFAULT_ENV to start with" in result.summary


def test_cli_registry_exposes_v2_command_tree_and_policies() -> None:
    registry = app._cli_core_yo_registry

    assert registry.resolve_command_args(["version"]) is not None
    assert registry.resolve_command_args(["config", "status"]) is not None
    assert registry.resolve_command_args(["gui", "status"]) is not None
    assert registry.resolve_command_args(["printer", "list"]) is not None
    assert registry.resolve_command_args(["template", "delete"]) is not None
    assert registry.resolve_command_args(["tapdb", "db"]) is not None
    assert registry.resolve_command_args(["cognito", "status"]) is not None
    assert registry.resolve_command_args(["users", "grant-admin"]) is not None

    version_cmd = registry.get_command(("version",))
    config_status_cmd = registry.get_command(("config", "status"))
    gui_status_cmd = registry.get_command(("gui", "status"))
    printer_list_cmd = registry.get_command(("printer", "list"))
    template_delete_cmd = registry.get_command(("template", "delete"))
    tapdb_db_cmd = registry.get_command(("tapdb", "db"))

    assert version_cmd is not None
    assert version_cmd.policy.runtime_guard == "exempt"

    assert config_status_cmd is not None
    assert config_status_cmd.policy.supports_json is True
    assert config_status_cmd.policy.runtime_guard == "exempt"

    assert gui_status_cmd is not None
    assert gui_status_cmd.policy.prereq_tags == {"zebra-runtime"}

    assert printer_list_cmd is not None
    assert printer_list_cmd.policy.supports_json is True
    assert printer_list_cmd.policy.prereq_tags == {"zebra-runtime"}

    assert template_delete_cmd is not None
    assert template_delete_cmd.policy.mutates_state is True
    assert template_delete_cmd.policy.interactive is True

    assert tapdb_db_cmd is not None
    assert tapdb_db_cmd.policy.mutates_state is True


def test_root_json_is_global_for_version() -> None:
    result = runner.invoke(app, ["--json", "version"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["app"] == "zebra_day"


def test_json_rejected_for_non_json_command() -> None:
    result = runner.invoke(app, ["--json", "gui", "status"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "contract_violation"
    assert payload["error"]["details"]["command"] == "gui/status"


def test_runtime_exempt_command_bypasses_runtime_guard(monkeypatch) -> None:
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)

    result = runner.invoke(app, ["--json", "version"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["app"] == "zebra_day"


def test_runtime_required_command_fails_without_active_env(monkeypatch) -> None:
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)

    result = runner.invoke(app, ["--json", "printer", "list"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "runtime_validation_failed"
    assert payload["error"]["details"]["summary"]["blocking_failures"] >= 1
