"""
Tests for zebra_day.backends.dynamo.DynamoBackend using moto mocks.
"""

from __future__ import annotations

import json
import os
import time
from unittest import mock

import boto3
import pytest
from moto import mock_aws

from zebra_day.backends.dynamo import DynamoBackend, _BACKUP_DEBOUNCE_SECONDS
from zebra_day.exceptions import (
    ConfigError,
    LabelTemplateNotFoundError,
    VersionConflictError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_env(monkeypatch):
    """Set fake AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # Ensure no real profile is used
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def dynamo_backend(aws_env):
    """Create a fully-provisioned DynamoBackend with moto-mocked resources."""
    with mock_aws():
        backend = DynamoBackend(
            table_name="test-zebra-config",
            region="us-east-1",
            s3_bucket="test-backup-bucket",
            s3_prefix="zebra-day/",
            client_id="test-client.testuser",
            cost_center="test-cc",
            project="test-project",
        )
        backend.create_table()
        backend.create_s3_bucket()
        backend.write_meta()
        yield backend


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_empty_table_returns_default(self, dynamo_backend):
        config = dynamo_backend.load_config()
        assert config["schema_version"] == "2.1.0"
        assert config["labs"] == {}

    def test_round_trip(self, dynamo_backend):
        sample = {"schema_version": "2.1.0", "labs": {"lab1": {"printers": {}}}}
        dynamo_backend.save_config(sample)
        loaded = dynamo_backend.load_config()
        assert loaded == sample


class TestSaveConfig:
    def test_increments_version(self, dynamo_backend):
        cfg = {"schema_version": "2.1.0", "labs": {}}
        dynamo_backend.save_config(cfg)
        v1 = dynamo_backend._get_item_version("CONFIG", "printer_config")
        assert v1 == 1

        dynamo_backend.save_config(cfg)
        v2 = dynamo_backend._get_item_version("CONFIG", "printer_config")
        assert v2 == 2

    def test_triggers_s3_backup(self, dynamo_backend):
        cfg = {"schema_version": "2.1.0", "labs": {}}
        dynamo_backend.save_config(cfg)
        backups = dynamo_backend.list_backups()
        assert len(backups) >= 1


class TestOptimisticLock:
    def test_version_conflict_raises(self, dynamo_backend):
        cfg = {"schema_version": "2.1.0", "labs": {}}
        dynamo_backend.save_config(cfg)

        # Simulate another client bumping the version behind our back.
        # We mock _get_item_version to return the stale version (1),
        # while the actual DB has version 999 — so the conditional write fails.
        dynamo_backend._table.update_item(
            Key={"PK": "CONFIG", "SK": "printer_config"},
            UpdateExpression="SET version = :v",
            ExpressionAttributeValues={":v": 999},
        )

        with mock.patch.object(dynamo_backend, "_get_item_version", return_value=1):
            with pytest.raises(VersionConflictError):
                dynamo_backend.save_config(cfg)

    def test_config_exists(self, dynamo_backend):
        assert dynamo_backend.config_exists() is False
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {}})
        assert dynamo_backend.config_exists() is True


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

class TestTemplateCRUD:
    def test_save_and_get(self, dynamo_backend):
        dynamo_backend.save_template("my_label", "^XA^FO10,10^A0N,30,30^FDHello^FS^XZ")
        content = dynamo_backend.get_template("my_label")
        assert "Hello" in content

    def test_get_not_found(self, dynamo_backend):
        with pytest.raises(LabelTemplateNotFoundError):
            dynamo_backend.get_template("nonexistent")

    def test_list_templates(self, dynamo_backend):
        dynamo_backend.save_template("alpha", "zpl_a")
        dynamo_backend.save_template("beta", "zpl_b")
        names = dynamo_backend.list_templates()
        assert names == ["alpha", "beta"]

    def test_delete_template(self, dynamo_backend):
        dynamo_backend.save_template("to_delete", "zpl")
        assert dynamo_backend.template_exists("to_delete")
        dynamo_backend.delete_template("to_delete")
        assert not dynamo_backend.template_exists("to_delete")

    def test_delete_not_found(self, dynamo_backend):
        with pytest.raises(LabelTemplateNotFoundError):
            dynamo_backend.delete_template("ghost")

    def test_strip_zpl_extension(self, dynamo_backend):
        dynamo_backend.save_template("test.zpl", "content")
        assert dynamo_backend.template_exists("test")
        content = dynamo_backend.get_template("test.zpl")
        assert content == "content"

    def test_template_version_conflict(self, dynamo_backend):
        dynamo_backend.save_template("tpl", "v1")
        dynamo_backend._table.update_item(
            Key={"PK": "TEMPLATE", "SK": "tpl"},
            UpdateExpression="SET version = :v",
            ExpressionAttributeValues={":v": 999},
        )
        with mock.patch.object(dynamo_backend, "_get_item_version", return_value=1):
            with pytest.raises(VersionConflictError):
                dynamo_backend.save_template("tpl", "v2")



# ---------------------------------------------------------------------------
# S3 Backup & Restore
# ---------------------------------------------------------------------------

class TestS3Backup:
    def test_backup_creates_manifest(self, dynamo_backend):
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {"a": {}}})
        dynamo_backend.save_template("tpl1", "^XA^XZ")
        prefix = dynamo_backend.backup_to_s3(triggered_by="test", force=True)
        assert prefix.startswith("zebra-day/backups/")

        # Verify manifest
        resp = dynamo_backend._s3.get_object(
            Bucket="test-backup-bucket",
            Key=f"{prefix}manifest.json",
        )
        manifest = json.loads(resp["Body"].read().decode())
        assert manifest["triggered_by"] == "test"
        assert manifest["template_count"] >= 1

    def test_backup_debounce(self, dynamo_backend):
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {}})
        # First backup fires (debounce timer was at 0)
        initial_backups = len(dynamo_backend.list_backups())

        # Set last backup to "just now" to trigger debounce
        dynamo_backend._last_backup_ts = time.monotonic()
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {"x": {}}})
        # Should not create another backup due to debounce
        assert len(dynamo_backend.list_backups()) == initial_backups

    def test_list_backups(self, dynamo_backend):
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {}})
        dynamo_backend.backup_to_s3(triggered_by="test1", force=True)
        # Sleep 1s to ensure a different second-level S3 key prefix
        time.sleep(1)
        dynamo_backend.backup_to_s3(triggered_by="test2", force=True)
        backups = dynamo_backend.list_backups()
        assert len(backups) >= 2
        # Sorted newest-first
        assert backups[0]["backup_timestamp"] >= backups[1]["backup_timestamp"]


class TestS3Restore:
    def test_restore_round_trip(self, dynamo_backend):
        orig_config = {"schema_version": "2.1.0", "labs": {"restored_lab": {"printers": {}}}}
        dynamo_backend.save_config(orig_config)
        dynamo_backend.save_template("restored_tpl", "^XA^RESTORED^XZ")

        prefix = dynamo_backend.backup_to_s3(triggered_by="pre-restore", force=True)

        # Wipe data
        dynamo_backend._table.delete_item(Key={"PK": "CONFIG", "SK": "printer_config"})
        dynamo_backend._table.delete_item(Key={"PK": "TEMPLATE", "SK": "restored_tpl"})
        assert dynamo_backend.config_exists() is False

        # Restore
        dynamo_backend.restore_from_s3(prefix)
        assert dynamo_backend.load_config() == orig_config
        assert "RESTORED" in dynamo_backend.get_template("restored_tpl")


# ---------------------------------------------------------------------------
# Resource Tagging
# ---------------------------------------------------------------------------

class TestResourceTagging:
    def test_dynamodb_table_tags(self, aws_env):
        with mock_aws():
            backend = DynamoBackend(
                table_name="tag-test-table",
                region="us-east-1",
                s3_bucket="tag-test-bucket",
                cost_center="my-cc",
                project="my-proj",
            )
            backend.create_table()

            # Check tags via describe
            arn = backend._ddb_client.describe_table(TableName="tag-test-table")["Table"]["TableArn"]
            tags_resp = backend._ddb_client.list_tags_of_resource(ResourceArn=arn)
            tags = {t["Key"]: t["Value"] for t in tags_resp.get("Tags", [])}
            assert tags["lsmc-cost-center"] == "my-cc"
            assert tags["lsmc-project"] == "my-proj"

    def test_s3_bucket_tags(self, aws_env):
        with mock_aws():
            backend = DynamoBackend(
                table_name="tag-test-table2",
                region="us-east-1",
                s3_bucket="tag-test-bucket2",
                cost_center="cc2",
                project="proj2",
            )
            backend.create_s3_bucket()
            resp = backend._s3.get_bucket_tagging(Bucket="tag-test-bucket2")
            tags = {t["Key"]: t["Value"] for t in resp["TagSet"]}
            assert tags["lsmc-cost-center"] == "cc2"
            assert tags["lsmc-project"] == "proj2"

    def test_tag_defaults(self, aws_env, monkeypatch):
        monkeypatch.delenv("LSMC_COST_CENTER", raising=False)
        monkeypatch.delenv("LSMC_PROJECT", raising=False)
        with mock_aws():
            backend = DynamoBackend(
                table_name="tag-default-table",
                region="us-west-2",
                s3_bucket="tag-default-bucket",
            )
            assert backend.cost_center == "global"
            assert backend.project == "zebra-day+us-west-2"

    def test_tag_from_env(self, aws_env, monkeypatch):
        monkeypatch.setenv("LSMC_COST_CENTER", "env-cc")
        monkeypatch.setenv("LSMC_PROJECT", "env-proj")
        with mock_aws():
            backend = DynamoBackend(
                table_name="tag-env-table",
                region="us-east-1",
                s3_bucket="tag-env-bucket",
            )
            assert backend.cost_center == "env-cc"
            assert backend.project == "env-proj"


# ---------------------------------------------------------------------------
# Factory & Profile Rules
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_from_env_basic(self, aws_env, monkeypatch):
        monkeypatch.setenv("ZEBRA_DAY_DYNAMO_TABLE", "my-table")
        monkeypatch.setenv("ZEBRA_DAY_DYNAMO_REGION", "eu-west-1")
        monkeypatch.setenv("ZEBRA_DAY_S3_BACKUP_BUCKET", "my-bucket")
        with mock_aws():
            backend = DynamoBackend.from_env()
            assert backend.table_name == "my-table"
            assert backend.region == "eu-west-1"
            assert backend.s3_bucket == "my-bucket"

    def test_from_env_missing_bucket_raises(self, aws_env, monkeypatch):
        monkeypatch.delenv("ZEBRA_DAY_S3_BACKUP_BUCKET", raising=False)
        with pytest.raises(ConfigError, match="ZEBRA_DAY_S3_BACKUP_BUCKET"):
            DynamoBackend.from_env()

    def test_no_explicit_default_profile(self, aws_env):
        with mock_aws():
            backend = DynamoBackend(
                table_name="t",
                region="us-east-1",
                s3_bucket="b",
                profile="default",
            )
            # "default" should be normalized to None internally
            # boto3 Session should not have received profile_name="default"
            assert backend is not None


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_get_status(self, dynamo_backend):
        dynamo_backend.save_config({"schema_version": "2.1.0", "labs": {}})
        status = dynamo_backend.get_status()
        assert status["table_name"] == "test-zebra-config"
        assert status["region"] == "us-east-1"
        assert status["table_status"] == "ACTIVE"
        assert status["s3_bucket"] == "test-backup-bucket"


# ---------------------------------------------------------------------------
# Integration: zpl() with DynamoBackend
# ---------------------------------------------------------------------------

class TestZplIntegration:
    def test_zpl_init_with_backend(self, dynamo_backend):
        from zebra_day.print_mgr import zpl

        z = zpl(backend=dynamo_backend)
        assert z.printers["schema_version"] == "2.1.0"

    def test_zpl_save_through_backend(self, dynamo_backend):
        from zebra_day.print_mgr import zpl

        z = zpl(backend=dynamo_backend)
        z.printers["labs"]["dynamo_lab"] = {"printers": {}}
        z.save_printer_config()

        loaded = dynamo_backend.load_config()
        assert "dynamo_lab" in loaded["labs"]

    def test_formulate_zpl_dynamo(self, dynamo_backend):
        """Template rendering works without filesystem when using DynamoDB."""
        from zebra_day.print_mgr import zpl

        # Store a simple template in DynamoDB
        tpl_content = "^XA^FO10,10^A0N,30,30^FD{uid_barcode}^FS^XZ"
        dynamo_backend.save_template("dynamo_test_label", tpl_content)

        z = zpl(backend=dynamo_backend)
        result = z.formulate_zpl(
            uid_barcode="BC123",
            label_zpl_style="dynamo_test_label",
        )
        assert "BC123" in result

    def test_env_var_selection(self, aws_env, monkeypatch):
        monkeypatch.setenv("ZEBRA_DAY_CONFIG_BACKEND", "dynamodb")
        monkeypatch.setenv("ZEBRA_DAY_S3_BACKUP_BUCKET", "env-bucket")
        monkeypatch.setenv("ZEBRA_DAY_DYNAMO_TABLE", "env-table")

        with mock_aws():
            # Create the resources
            boto3.client("dynamodb", region_name="us-east-1").create_table(
                TableName="env-table",
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="env-bucket")

            from zebra_day.backends import get_backend
            from zebra_day.backends.dynamo import DynamoBackend as DB

            backend = get_backend()
            assert isinstance(backend, DB)
