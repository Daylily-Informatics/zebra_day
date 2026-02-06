"""
Tests for the zday dynamo CLI subcommand group using moto mocks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from typer.testing import CliRunner

from zebra_day.cli import app

runner = CliRunner()

# Reusable env var dict for mocked AWS credentials + required settings
_DYNAMO_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
    "ZEBRA_DAY_S3_BACKUP_BUCKET": "test-backup-bucket",
    "ZEBRA_DAY_DYNAMO_TABLE": "test-zebra-config",
    "ZEBRA_DAY_DYNAMO_REGION": "us-east-1",
    "ZEBRA_DAY_S3_BACKUP_PREFIX": "zebra-day/",
}


@pytest.fixture
def aws_env(monkeypatch):
    """Set fake AWS credentials for moto."""
    for k, v in _DYNAMO_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def _provision_resources():
    """Provision DynamoDB table + S3 bucket inside moto mock context."""
    from zebra_day.backends.dynamo import DynamoBackend

    backend = DynamoBackend(
        table_name="test-zebra-config",
        region="us-east-1",
        s3_bucket="test-backup-bucket",
        s3_prefix="zebra-day/",
        client_id="test-client.testuser",
    )
    backend.create_table()
    backend.create_s3_bucket()
    backend.write_meta()
    return backend


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestDynamoInit:
    def test_init_success(self, aws_env):
        with mock_aws():
            result = runner.invoke(
                app,
                [
                    "dynamo", "init",
                    "--table-name", "test-zebra-config",
                    "--s3-bucket", "test-backup-bucket",
                    "--region", "us-east-1",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "created and active" in result.output or "already exists" in result.output
            assert "ZEBRA_DAY_CONFIG_BACKEND=dynamodb" in result.output

    def test_init_missing_s3_bucket(self, aws_env, monkeypatch):
        monkeypatch.delenv("ZEBRA_DAY_S3_BACKUP_BUCKET", raising=False)
        with mock_aws():
            result = runner.invoke(
                app,
                ["dynamo", "init", "--table-name", "test-zebra-config", "--region", "us-east-1"],
            )
            assert result.exit_code == 1
            assert "S3 bucket required" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestDynamoStatus:
    def test_status_success(self, aws_env):
        with mock_aws():
            _provision_resources()
            result = runner.invoke(app, ["dynamo", "status"])
            assert result.exit_code == 0, result.output
            assert "test-zebra-config" in result.output

    def test_status_json(self, aws_env):
        with mock_aws():
            _provision_resources()
            result = runner.invoke(app, ["dynamo", "status", "--json"])
            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["table_name"] == "test-zebra-config"

    def test_status_no_bucket_env(self, aws_env, monkeypatch):
        monkeypatch.delenv("ZEBRA_DAY_S3_BACKUP_BUCKET", raising=False)
        result = runner.invoke(app, ["dynamo", "status"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


class TestDynamoBootstrap:
    def test_bootstrap_with_config_and_templates(self, aws_env, tmp_path):
        # Create a minimal config file
        cfg = tmp_path / "config.yaml"
        cfg.write_text("labs: {}\n")
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "test_label.zpl").write_text("^XA^FDtest^FS^XZ")

        with mock_aws():
            _provision_resources()
            result = runner.invoke(
                app,
                [
                    "dynamo", "bootstrap",
                    "--config-file", str(cfg),
                    "--templates-dir", str(tpl_dir),
                    "--no-include-package",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Config uploaded" in result.output
            assert "1 template(s) uploaded" in result.output
            assert "Backup written" in result.output




# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


class TestDynamoExport:
    def test_export_json(self, aws_env, tmp_path):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {"lab1": {}}})
            backend.save_template("tube_2inX1in", "^XA^FDtube^FS^XZ")

            out_dir = tmp_path / "export-out"
            result = runner.invoke(
                app,
                ["dynamo", "export", "--output-dir", str(out_dir), "--format", "json"],
            )
            assert result.exit_code == 0, result.output
            assert "Config written" in result.output
            assert "1 template(s)" in result.output

            # Verify files
            cfg = out_dir / "config.json"
            assert cfg.exists()
            data = json.loads(cfg.read_text())
            assert "labs" in data

            tpl = out_dir / "templates" / "tube_2inX1in.zpl"
            assert tpl.exists()
            assert "^XA" in tpl.read_text()

    def test_export_yaml(self, aws_env, tmp_path):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {}})

            out_dir = tmp_path / "export-yaml"
            result = runner.invoke(
                app,
                ["dynamo", "export", "--output-dir", str(out_dir), "--format", "yaml"],
            )
            assert result.exit_code == 0, result.output
            assert (out_dir / "config.yaml").exists()


# ---------------------------------------------------------------------------
# backup
# ---------------------------------------------------------------------------


class TestDynamoBackup:
    def test_backup_success(self, aws_env):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {}})

            result = runner.invoke(app, ["dynamo", "backup"])
            assert result.exit_code == 0, result.output
            assert "Backup written" in result.output

    def test_backup_no_env(self, aws_env, monkeypatch):
        monkeypatch.delenv("ZEBRA_DAY_S3_BACKUP_BUCKET", raising=False)
        result = runner.invoke(app, ["dynamo", "backup"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


class TestDynamoRestore:
    def test_restore_list(self, aws_env):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {}})
            backend.backup_to_s3(triggered_by="test", force=True)

            result = runner.invoke(app, ["dynamo", "restore", "--list"])
            assert result.exit_code == 0, result.output
            assert "test" in result.output or "Timestamp" in result.output

    def test_restore_list_empty(self, aws_env):
        with mock_aws():
            _provision_resources()

            result = runner.invoke(app, ["dynamo", "restore", "--list"])
            assert result.exit_code == 0

    def test_restore_missing_key(self, aws_env):
        with mock_aws():
            _provision_resources()
            result = runner.invoke(app, ["dynamo", "restore"])
            assert result.exit_code == 1
            assert "--s3-key" in result.output

    def test_restore_success(self, aws_env):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {"lab1": {}}})
            backend.save_template("t1", "^XA^FDt1^FS^XZ")
            prefix = backend.backup_to_s3(triggered_by="pre-restore-test", force=True)

            # Wipe current data
            backend.save_config({"labs": {}})

            result = runner.invoke(
                app,
                ["dynamo", "restore", "--s3-key", prefix, "--yes"],
            )
            assert result.exit_code == 0, result.output
            assert "Restore complete" in result.output

            # Verify config was restored
            restored_cfg = backend.load_config()
            assert "lab1" in restored_cfg.get("labs", {})


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDynamoDestroy:
    def test_destroy_requires_yes(self, aws_env):
        with mock_aws():
            _provision_resources()
            result = runner.invoke(app, ["dynamo", "destroy"])
            assert result.exit_code == 1
            assert "--yes" in result.output

    def test_destroy_success(self, aws_env):
        with mock_aws():
            backend = _provision_resources()
            backend.save_config({"labs": {}})

            result = runner.invoke(app, ["dynamo", "destroy", "--yes"])
            assert result.exit_code == 0, result.output
            assert "Table deleted" in result.output
            assert "Backups preserved" in result.output
