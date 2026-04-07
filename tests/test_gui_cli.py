from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

import zebra_day.cli as zebra_cli
from zebra_day.cli import gui as gui_module

runner = CliRunner()


def _set_xdg(monkeypatch, tmp_path, deployment="local") -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("ZEBRA_DAY_DEPLOYMENT_CODE", deployment)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", f"ZEBRA_DAY-{deployment}")
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda" / deployment))


def test_gui_start_uses_shared_tls_contract(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path, deployment="jemtest")
    cert_dir = tmp_path / "state" / "dayhoff" / "jemtest" / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    cert_file.write_text("cert", encoding="utf-8")
    key_file.write_text("key", encoding="utf-8")

    calls: dict[str, object] = {}

    class _Process:
        pid = 43210

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(gui_module, "_ensure_runtime_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_module, "_running_pid", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_module, "_log_file", lambda settings: tmp_path / "gui.log")
    monkeypatch.setattr(gui_module, "_pid_file", lambda settings: tmp_path / "gui.pid")
    monkeypatch.setattr(
        gui_module, "_runtime_meta_file", lambda settings: tmp_path / "server-meta.json"
    )
    monkeypatch.setattr(
        gui_module,
        "resolve_https_certs",
        lambda **kwargs: SimpleNamespace(
            cert_path=cert_file,
            key_path=key_file,
            source="test",
        ),
    )
    monkeypatch.setattr(
        gui_module,
        "shared_dayhoff_certs_dir",
        lambda deployment_code: cert_dir,
    )

    def fake_popen(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = kwargs["env"]
        return _Process()

    monkeypatch.setattr(
        gui_module,
        "subprocess",
        SimpleNamespace(
            Popen=fake_popen, run=gui_module.subprocess.run, STDOUT=gui_module.subprocess.STDOUT
        ),
    )

    result = runner.invoke(
        zebra_cli.app,
        ["gui", "start", "--background", "--host", "0.0.0.0", "--port", "8118"],
    )

    assert result.exit_code == 0
    assert "https://localhost:8118" in result.output
    assert "SSL_CERT_FILE" not in calls["env"]
    assert "SSL_KEY_FILE" not in calls["env"]
    assert "SSL_CERT_PATH" not in calls["env"]
    assert "SSL_KEY_PATH" not in calls["env"]
    assert "ssl_enabled=True" in calls["cmd"][2]
    assert str(cert_file) in calls["cmd"][2]
    assert str(key_file) in calls["cmd"][2]


def test_gui_start_supports_deprecated_no_https_alias(monkeypatch, tmp_path):
    _set_xdg(monkeypatch, tmp_path)

    class _Process:
        pid = 56789

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(gui_module, "_ensure_runtime_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_module, "_running_pid", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_module, "_log_file", lambda settings: tmp_path / "gui.log")
    monkeypatch.setattr(gui_module, "_pid_file", lambda settings: tmp_path / "gui.pid")
    monkeypatch.setattr(
        gui_module, "_runtime_meta_file", lambda settings: tmp_path / "server-meta.json"
    )
    monkeypatch.setattr(
        gui_module,
        "resolve_https_certs",
        lambda **kwargs: SimpleNamespace(
            cert_path=tmp_path / "state" / "dayhoff" / "local" / "certs" / "cert.pem",
            key_path=tmp_path / "state" / "dayhoff" / "local" / "certs" / "key.pem",
            source="test",
        ),
    )
    monkeypatch.setattr(
        gui_module,
        "shared_dayhoff_certs_dir",
        lambda deployment_code: tmp_path / "state" / "dayhoff" / deployment_code / "certs",
    )

    def fake_popen(cmd, **kwargs):
        return _Process()

    monkeypatch.setattr(
        gui_module,
        "subprocess",
        SimpleNamespace(
            Popen=fake_popen, run=gui_module.subprocess.run, STDOUT=gui_module.subprocess.STDOUT
        ),
    )

    result = runner.invoke(zebra_cli.app, ["gui", "start", "--background", "--no-https"])

    assert result.exit_code == 0
    assert "http://localhost:8118" in result.output


def test_gui_status_reads_runtime_meta(monkeypatch, tmp_path, capsys):
    _set_xdg(monkeypatch, tmp_path)
    meta_path = tmp_path / "server-meta.json"
    meta_path.write_text('{"host":"0.0.0.0","port":8118,"ssl_enabled":false}', encoding="utf-8")

    monkeypatch.setattr(gui_module, "_running_pid", lambda *args, **kwargs: 12345)
    monkeypatch.setattr(gui_module, "_runtime_meta_file", lambda settings: meta_path)
    monkeypatch.setattr(
        gui_module,
        "ZebraDaySettings",
        SimpleNamespace(
            from_context=lambda: SimpleNamespace(
                host="localhost",
                port=9000,
                state_dir=tmp_path,
                logs_dir=tmp_path,
            )
        ),
    )

    gui_module.status()
    captured = capsys.readouterr()
    assert "http://localhost:8118" in captured.out
