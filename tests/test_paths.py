from __future__ import annotations

from pathlib import Path

from zebra_day import paths as xdg


def _isolate_xdg_dirs(tmp_path: Path, monkeypatch, deployment: str = "local2") -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg_state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg_cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)


def test_config_path_is_deployment_scoped(tmp_path, monkeypatch):
    _isolate_xdg_dirs(tmp_path, monkeypatch, deployment="qa-1")
    assert xdg.get_config_dir() == tmp_path / "xdg_config" / "zebra_day"
    assert (
        xdg.get_config_file_path()
        == tmp_path / "xdg_config" / "zebra_day" / "zebra-day-config-qa-1.yaml"
    )


def test_data_state_and_cache_dirs_include_deployment(tmp_path, monkeypatch):
    _isolate_xdg_dirs(tmp_path, monkeypatch, deployment="demo")
    assert xdg.get_data_dir() == tmp_path / "xdg_data" / "zebra_day" / "demo"
    assert xdg.get_state_dir() == tmp_path / "xdg_state" / "zebra_day" / "demo"
    assert xdg.get_cache_dir() == tmp_path / "xdg_cache" / "zebra_day" / "demo"
    assert xdg.get_logs_dir() == tmp_path / "xdg_state" / "zebra_day" / "demo" / "logs"
    assert (
        xdg.get_generated_files_dir() == tmp_path / "xdg_cache" / "zebra_day" / "demo" / "generated"
    )


def test_sanitize_deployment_code_normalizes_bad_characters():
    assert xdg.sanitize_deployment_code("prod east/1") == "prod-east-1"
