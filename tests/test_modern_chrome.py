from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from zebra_day.web.chrome import (
    build_chrome_context,
    deployment_color,
    region_color,
    resolve_git_metadata,
)


def test_deployment_color_vectors_are_canonical() -> None:
    assert deployment_color("510x2") == "#4321ca"
    assert deployment_color("inflec3") == "#7521ca"
    assert deployment_color("production") == "#ca2183"


def test_region_color_vectors_are_canonical() -> None:
    assert region_color("us-east-1") == "#8aca72"
    assert region_color("us-west-2") == "#a5ca72"


def test_build_chrome_context_uses_environment_chrome_toggle_and_canonical_colors() -> None:
    settings = SimpleNamespace(
        deployment_code="510x2",
        deployment_name="510x2",
        deployment_is_production=False,
        tapdb_env="us-east-1",
        ui_show_environment_chrome=False,
    )

    chrome = build_chrome_context(settings)

    assert chrome["show_environment_chrome"] is False
    assert chrome["deployment"] == {
        "name": "510x2",
        "label": "510X2",
        "color": "#4321ca",
        "is_production": False,
    }
    assert chrome["region"] == {
        "name": "us-east-1",
        "label": "US-EAST-1",
        "color": "#8aca72",
    }


def test_resolve_git_metadata_uses_exact_match_tag(monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []

    def _run(cmd, check, capture_output, text):  # noqa: ANN001
        del check, capture_output, text
        commands.append(tuple(cmd))
        if cmd[:3] == ["git", "-C", "/tmp/repo"] and cmd[3:] == [
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        ]:
            return SimpleNamespace(returncode=0, stdout="codex/zebra-day-gui-chrome-scm\n")
        if cmd[:3] == ["git", "-C", "/tmp/repo"] and cmd[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(
                returncode=0, stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
            )
        if cmd[:3] == ["git", "-C", "/tmp/repo"] and cmd[3:] == [
            "describe",
            "--tags",
            "--exact-match",
            "HEAD",
        ]:
            return SimpleNamespace(returncode=0, stdout="v2.4.6\n")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr("subprocess.run", _run)

    metadata = resolve_git_metadata(Path("/tmp/repo"))

    assert metadata.branch == "codex/zebra-day-gui-chrome-scm"
    assert metadata.tag == "v2.4.6"
    assert metadata.commit == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert metadata.short_commit == "deadbeefdead"
    assert commands
