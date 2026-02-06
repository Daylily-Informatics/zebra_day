"""
DynamoDB + S3 backend for zebra_day config + template storage.

Implements the ``ConfigBackend`` protocol using a single DynamoDB table
(PK/SK design) with automatic S3 backup on every write (debounced).
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import platform
import time
from decimal import Decimal
from typing import Any

from zebra_day.exceptions import ConfigError, LabelTemplateNotFoundError, VersionConflictError
from zebra_day.logging_config import get_logger

_log = get_logger(__name__)

# Debounce interval for S3 backups (seconds)
_BACKUP_DEBOUNCE_SECONDS = 60


class DynamoBackend:
    """DynamoDB-backed config and template backend with S3 backup."""

    def __init__(
        self,
        table_name: str = "zebra-day-config",
        region: str | None = None,
        s3_bucket: str | None = None,
        s3_prefix: str = "zebra-day/",
        client_id: str | None = None,
        cost_center: str | None = None,
        project: str | None = None,
        profile: str | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for the DynamoDB backend. "
                "Install with: pip install zebra_day[aws]"
            ) from None

        # Never pass profile_name="default" explicitly
        if profile and profile.lower() == "default":
            profile = None

        self.table_name = table_name
        self.region = region or "us-east-1"
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix.rstrip("/") + "/" if s3_prefix else "zebra-day/"
        self.client_id = client_id or f"{platform.node()}.{getpass.getuser()}"
        self.cost_center = cost_center or os.environ.get("LSMC_COST_CENTER", "global")
        self.project = project or os.environ.get(
            "LSMC_PROJECT", f"zebra-day+{self.region}"
        )

        session_kwargs: dict[str, Any] = {"region_name": self.region}
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        self._ddb_resource = session.resource("dynamodb")
        self._ddb_client = session.client("dynamodb")
        self._s3 = session.client("s3")
        self._table = self._ddb_resource.Table(self.table_name)

        # Debounce tracking
        self._last_backup_ts: float = 0.0

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "DynamoBackend":
        """Create a DynamoBackend from environment variables."""
        table = os.environ.get("ZEBRA_DAY_DYNAMO_TABLE", "zebra-day-config")
        region = os.environ.get(
            "ZEBRA_DAY_DYNAMO_REGION",
            os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
        s3_bucket = os.environ.get("ZEBRA_DAY_S3_BACKUP_BUCKET", "")
        s3_prefix = os.environ.get("ZEBRA_DAY_S3_BACKUP_PREFIX", "zebra-day/")
        client_id = os.environ.get(
            "ZEBRA_DAY_CLIENT_ID",
            f"{platform.node()}.{getpass.getuser()}",
        )
        profile = os.environ.get("AWS_PROFILE") or None

        if not s3_bucket:
            raise ConfigError(
                "ZEBRA_DAY_S3_BACKUP_BUCKET is required when using DynamoDB backend. "
                "Set it to the S3 bucket name for config backups."
            )

        return cls(
            table_name=table,
            region=region,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            client_id=client_id,
            profile=profile,
        )

    # ------------------------------------------------------------------
    # AWS permission pre-flight checks
    # ------------------------------------------------------------------

    def check_aws_permissions(self) -> dict[str, Any]:
        """Verify AWS credentials and permissions before resource creation.

        Returns a dict with:
          - identity: STS caller identity info (or error)
          - checks: list of {action, ok, detail} dicts
          - all_ok: bool — True if all checks passed
        """
        import botocore.exceptions

        result: dict[str, Any] = {"identity": {}, "checks": [], "all_ok": True}

        # 1. STS identity check — do credentials work at all?
        try:
            sts = self._ddb_resource.meta.client.meta.events
            # Use the session to create an STS client
            session_kwargs: dict[str, Any] = {"region_name": self.region}
            import boto3 as _b3

            sts_client = _b3.Session(**session_kwargs).client("sts")
            identity = sts_client.get_caller_identity()
            result["identity"] = {
                "account": identity.get("Account", "?"),
                "arn": identity.get("Arn", "?"),
                "user_id": identity.get("UserId", "?"),
            }
            result["checks"].append(
                {"action": "sts:GetCallerIdentity", "ok": True, "detail": identity.get("Arn", "")}
            )
        except Exception as exc:
            result["identity"] = {"error": str(exc)}
            result["checks"].append(
                {"action": "sts:GetCallerIdentity", "ok": False, "detail": str(exc)}
            )
            result["all_ok"] = False
            return result  # No point continuing if creds don't work

        # 2. DynamoDB — try ListTables (minimal read permission)
        try:
            self._ddb_client.list_tables(Limit=1)
            result["checks"].append(
                {"action": "dynamodb:ListTables", "ok": True, "detail": "accessible"}
            )
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            result["checks"].append(
                {"action": "dynamodb:ListTables", "ok": False, "detail": f"{code}: {exc}"}
            )
            result["all_ok"] = False

        # 3. DynamoDB — try DescribeTable (may not exist yet; 404 is fine)
        try:
            self._ddb_client.describe_table(TableName=self.table_name)
            result["checks"].append(
                {"action": "dynamodb:DescribeTable", "ok": True, "detail": "table exists"}
            )
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ResourceNotFoundException":
                result["checks"].append(
                    {"action": "dynamodb:DescribeTable", "ok": True, "detail": "table not found (will be created)"}
                )
            else:
                result["checks"].append(
                    {"action": "dynamodb:DescribeTable", "ok": False, "detail": f"{code}: {exc}"}
                )
                result["all_ok"] = False

        # 4. S3 — try HeadBucket (may not exist yet; 404 is fine)
        if self.s3_bucket:
            try:
                self._s3.head_bucket(Bucket=self.s3_bucket)
                result["checks"].append(
                    {"action": "s3:HeadBucket", "ok": True, "detail": "bucket exists"}
                )
            except botocore.exceptions.ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("404", "NoSuchBucket"):
                    result["checks"].append(
                        {"action": "s3:HeadBucket", "ok": True, "detail": "bucket not found (will be created)"}
                    )
                elif code == "403":
                    result["checks"].append(
                        {"action": "s3:HeadBucket", "ok": False, "detail": "access denied — check S3 permissions"}
                    )
                    result["all_ok"] = False
                else:
                    result["checks"].append(
                        {"action": "s3:HeadBucket", "ok": False, "detail": f"{code}: {exc}"}
                    )
                    result["all_ok"] = False

            # 5. S3 — try ListBuckets (verifies broad S3 access)
            try:
                self._s3.list_buckets()
                result["checks"].append(
                    {"action": "s3:ListBuckets", "ok": True, "detail": "accessible"}
                )
            except botocore.exceptions.ClientError as exc:
                code = exc.response["Error"]["Code"]
                result["checks"].append(
                    {"action": "s3:ListBuckets", "ok": False, "detail": f"{code}: {exc}"}
                )
                result["all_ok"] = False

        return result

    # ------------------------------------------------------------------
    # Resource provisioning
    # ------------------------------------------------------------------

    def create_table(self) -> None:
        """Create the DynamoDB table (used by `zday dynamo init`)."""
        tags = [
            {"Key": "lsmc-cost-center", "Value": self.cost_center},
            {"Key": "lsmc-project", "Value": self.project},
        ]

        self._ddb_client.create_table(
            TableName=self.table_name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
            Tags=tags,
        )

        # Wait for table to become active
        waiter = self._ddb_client.get_waiter("table_exists")
        waiter.wait(TableName=self.table_name)
        # Refresh the Table resource reference
        self._table = self._ddb_resource.Table(self.table_name)
        _log.info("DynamoDB table '%s' created and active", self.table_name)

    def create_s3_bucket(self) -> None:
        """Create the S3 backup bucket if it doesn't exist."""
        tags = [
            {"Key": "lsmc-cost-center", "Value": self.cost_center},
            {"Key": "lsmc-project", "Value": self.project},
        ]
        try:
            self._s3.head_bucket(Bucket=self.s3_bucket)
            _log.info("S3 bucket '%s' already exists", self.s3_bucket)
        except Exception:
            create_kwargs: dict[str, Any] = {"Bucket": self.s3_bucket}
            if self.region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.region,
                }
            self._s3.create_bucket(**create_kwargs)
            _log.info("S3 bucket '%s' created", self.s3_bucket)

        self._s3.put_bucket_tagging(
            Bucket=self.s3_bucket,
            Tagging={"TagSet": tags},
        )

    def write_meta(self) -> None:
        """Write the META#table_info item (used by `zday dynamo init`)."""
        from zebra_day import __version__

        now = datetime.datetime.now(datetime.UTC).isoformat()
        self._table.put_item(
            Item={
                "PK": "META",
                "SK": "table_info",
                "created_at": now,
                "created_by": self.client_id,
                "last_backup_at": "",
                "last_backup_s3_key": "",
                "zebra_day_version": __version__,
            }
        )

    def delete_table(self) -> None:
        """Delete the DynamoDB table (used by `zday dynamo destroy`)."""
        self._ddb_client.delete_table(TableName=self.table_name)
        _log.info("DynamoDB table '%s' deletion initiated", self.table_name)

    # ------------------------------------------------------------------
    # ConfigBackend protocol: config operations
    # ------------------------------------------------------------------

    def load_config(self) -> dict:
        """Load the printer configuration from DynamoDB."""
        try:
            resp = self._table.get_item(Key={"PK": "CONFIG", "SK": "printer_config"})
        except Exception as exc:
            raise ConfigError(f"Failed to load config from DynamoDB: {exc}") from exc

        item = resp.get("Item")
        if not item:
            # No config stored yet — return empty v2.1.0 config
            return {"schema_version": "2.1.0", "labs": {}}

        config_data = item.get("config_data", "{}")
        if isinstance(config_data, str):
            return json.loads(config_data)
        return dict(config_data)

    def save_config(self, config: dict) -> None:
        """Save the printer configuration to DynamoDB with optimistic locking."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        config_json = json.dumps(config, default=str)

        # Get current version
        current_version = self._get_item_version("CONFIG", "printer_config")

        item = {
            "PK": "CONFIG",
            "SK": "printer_config",
            "config_data": config_json,
            "schema_version": config.get("schema_version", "2.1.0"),
            "version": current_version + 1,
            "updated_at": now,
            "updated_by": self.client_id,
        }

        try:
            if current_version == 0:
                # New item — condition: item must not exist
                self._table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(PK)",
                )
            else:
                self._table.put_item(
                    Item=item,
                    ConditionExpression="#v = :expected",
                    ExpressionAttributeNames={"#v": "version"},
                    ExpressionAttributeValues={":expected": current_version},
                )
        except self._ddb_resource.meta.client.exceptions.ConditionalCheckFailedException:
            raise VersionConflictError("CONFIG#printer_config", current_version)

        _log.debug("Config saved to DynamoDB (version %d)", current_version + 1)
        self._maybe_backup("save_config")

    def config_exists(self) -> bool:
        """Check whether a config item exists in DynamoDB."""
        resp = self._table.get_item(
            Key={"PK": "CONFIG", "SK": "printer_config"},
            ProjectionExpression="PK",
        )
        return "Item" in resp

    # ------------------------------------------------------------------
    # ConfigBackend protocol: template operations
    # ------------------------------------------------------------------

    def get_template(self, name: str) -> str:
        """Load a template's ZPL content by stem name."""
        stem = self._normalize_stem(name)
        resp = self._table.get_item(Key={"PK": "TEMPLATE", "SK": stem})
        item = resp.get("Item")
        if not item:
            raise LabelTemplateNotFoundError(stem)
        return str(item["zpl_content"])

    def list_templates(self) -> list[str]:
        """List all template stem names from DynamoDB."""
        resp = self._table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": "TEMPLATE"},
            ProjectionExpression="SK",
        )
        return sorted(item["SK"] for item in resp.get("Items", []))

    def save_template(self, name: str, zpl_content: str) -> None:
        """Save or overwrite a template in DynamoDB with optimistic locking."""
        stem = self._normalize_stem(name)
        now = datetime.datetime.now(datetime.UTC).isoformat()
        current_version = self._get_item_version("TEMPLATE", stem)
        content = str(zpl_content)

        item = {
            "PK": "TEMPLATE",
            "SK": stem,
            "zpl_content": content,
            "filename": f"{stem}.zpl",
            "size_bytes": len(content.encode()),
            "version": current_version + 1,
            "updated_at": now,
            "updated_by": self.client_id,
        }

        try:
            if current_version == 0:
                self._table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(PK)",
                )
            else:
                self._table.put_item(
                    Item=item,
                    ConditionExpression="#v = :expected",
                    ExpressionAttributeNames={"#v": "version"},
                    ExpressionAttributeValues={":expected": current_version},
                )
        except self._ddb_resource.meta.client.exceptions.ConditionalCheckFailedException:
            raise VersionConflictError(f"TEMPLATE#{stem}", current_version)

        _log.debug("Template '%s' saved to DynamoDB (version %d)", stem, current_version + 1)
        self._maybe_backup("save_template")

    def delete_template(self, name: str) -> None:
        """Delete a template from DynamoDB."""
        stem = self._normalize_stem(name)
        # Verify it exists first
        if not self.template_exists(stem):
            raise LabelTemplateNotFoundError(stem)
        self._table.delete_item(Key={"PK": "TEMPLATE", "SK": stem})
        _log.debug("Template '%s' deleted from DynamoDB", stem)
        self._maybe_backup("delete_template")

    def template_exists(self, name: str) -> bool:
        """Check if a template exists in DynamoDB."""
        stem = self._normalize_stem(name)
        resp = self._table.get_item(
            Key={"PK": "TEMPLATE", "SK": stem},
            ProjectionExpression="PK",
        )
        return "Item" in resp


    # ------------------------------------------------------------------
    # S3 Backup
    # ------------------------------------------------------------------

    def backup_to_s3(self, *, triggered_by: str = "manual", force: bool = False) -> str:
        """Write a full snapshot to S3. Returns the S3 key prefix of the backup."""
        from zebra_day import __version__

        now = datetime.datetime.now(datetime.UTC)
        ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
        prefix = f"{self.s3_prefix}backups/{ts}/"

        # Gather data
        config = self.load_config()
        templates = self._all_templates()

        # config.json
        self._s3.put_object(
            Bucket=self.s3_bucket,
            Key=f"{prefix}config.json",
            Body=json.dumps(config, indent=2, default=str).encode(),
            ContentType="application/json",
        )

        # templates/
        for stem, content in templates.items():
            self._s3.put_object(
                Bucket=self.s3_bucket,
                Key=f"{prefix}templates/{stem}.zpl",
                Body=content.encode(),
                ContentType="text/plain",
            )

        # manifest.json
        config_version = self._get_item_version("CONFIG", "printer_config")
        manifest = {
            "backup_timestamp": now.isoformat(),
            "zebra_day_version": __version__,
            "schema_version": config.get("schema_version", "2.1.0"),
            "config_version": config_version,
            "template_count": len(templates),
            "templates": [
                {"name": stem, "size_bytes": len(content.encode())}
                for stem, content in templates.items()
            ],
            "triggered_by": triggered_by,
            "client_id": self.client_id,
        }
        self._s3.put_object(
            Bucket=self.s3_bucket,
            Key=f"{prefix}manifest.json",
            Body=json.dumps(manifest, indent=2).encode(),
            ContentType="application/json",
        )

        # Update META item with last backup info
        try:
            self._table.update_item(
                Key={"PK": "META", "SK": "table_info"},
                UpdateExpression="SET last_backup_at = :ts, last_backup_s3_key = :key",
                ExpressionAttributeValues={
                    ":ts": now.isoformat(),
                    ":key": prefix,
                },
            )
        except Exception:
            _log.warning("Could not update META item with backup info")

        self._last_backup_ts = time.monotonic()
        _log.info("Backup written to s3://%s/%s", self.s3_bucket, prefix)
        return prefix

    def list_backups(self) -> list[dict]:
        """List available S3 backups by scanning manifest.json files."""
        prefix = f"{self.s3_prefix}backups/"
        manifests: list[dict] = []

        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.s3_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith("/manifest.json"):
                    try:
                        resp = self._s3.get_object(Bucket=self.s3_bucket, Key=obj["Key"])
                        manifest = json.loads(resp["Body"].read().decode())
                        manifest["_s3_prefix"] = obj["Key"].rsplit("manifest.json", 1)[0]
                        manifests.append(manifest)
                    except Exception:
                        _log.warning("Could not read manifest: %s", obj["Key"])

        return sorted(manifests, key=lambda m: m.get("backup_timestamp", ""), reverse=True)

    def restore_from_s3(self, s3_prefix: str) -> None:
        """Restore config + templates from an S3 backup prefix."""
        # Read config
        config_key = f"{s3_prefix}config.json"
        resp = self._s3.get_object(Bucket=self.s3_bucket, Key=config_key)
        config = json.loads(resp["Body"].read().decode())

        # Write config to DDB (bypass optimistic locking for restore)
        now = datetime.datetime.now(datetime.UTC).isoformat()
        self._table.put_item(
            Item={
                "PK": "CONFIG",
                "SK": "printer_config",
                "config_data": json.dumps(config, default=str),
                "schema_version": config.get("schema_version", "2.1.0"),
                "version": 1,
                "updated_at": now,
                "updated_by": self.client_id,
            }
        )

        # List and restore templates
        tpl_prefix = f"{s3_prefix}templates/"
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.s3_bucket, Prefix=tpl_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".zpl"):
                    continue
                stem = key.rsplit("/", 1)[-1].replace(".zpl", "")
                tpl_resp = self._s3.get_object(Bucket=self.s3_bucket, Key=key)
                content = tpl_resp["Body"].read().decode()
                self._table.put_item(
                    Item={
                        "PK": "TEMPLATE",
                        "SK": stem,
                        "zpl_content": content,
                        "filename": f"{stem}.zpl",
                        "size_bytes": len(content.encode()),
                        "version": 1,
                        "updated_at": now,
                        "updated_by": self.client_id,
                    }
                )

        _log.info("Restore complete from s3://%s/%s", self.s3_bucket, s3_prefix)
        # Post-restore backup
        self.backup_to_s3(triggered_by="restore", force=True)

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Gather status info for `zday dynamo status`."""
        # Table info
        table_desc = self._ddb_client.describe_table(TableName=self.table_name)["Table"]
        item_count = table_desc.get("ItemCount", 0)
        table_status = table_desc.get("TableStatus", "UNKNOWN")

        # Meta item
        meta_resp = self._table.get_item(Key={"PK": "META", "SK": "table_info"})
        meta = meta_resp.get("Item", {})

        # Config version
        config_resp = self._table.get_item(
            Key={"PK": "CONFIG", "SK": "printer_config"},
            ProjectionExpression="version, updated_at, updated_by",
        )
        config_item = config_resp.get("Item", {})

        # Count backups
        backup_count = len(self.list_backups())

        return {
            "table_name": self.table_name,
            "region": self.region,
            "table_status": table_status,
            "item_count": item_count,
            "s3_bucket": self.s3_bucket,
            "s3_prefix": self.s3_prefix,
            "last_backup_at": meta.get("last_backup_at", ""),
            "last_backup_s3_key": meta.get("last_backup_s3_key", ""),
            "backup_count": backup_count,
            "config_version": int(config_item.get("version", 0)),
            "config_updated_at": config_item.get("updated_at", ""),
            "config_updated_by": config_item.get("updated_by", ""),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_item_version(self, pk: str, sk: str) -> int:
        """Get the current version of an item, or 0 if not found."""
        resp = self._table.get_item(
            Key={"PK": pk, "SK": sk},
            ProjectionExpression="version",
        )
        item = resp.get("Item")
        if not item:
            return 0
        v = item.get("version", 0)
        # DynamoDB returns Decimal for numbers
        return int(v) if isinstance(v, (int, Decimal)) else int(v)

    def _maybe_backup(self, triggered_by: str) -> None:
        """Trigger S3 backup if debounce interval has elapsed."""
        if not self.s3_bucket:
            return
        elapsed = time.monotonic() - self._last_backup_ts
        if elapsed >= _BACKUP_DEBOUNCE_SECONDS:
            try:
                self.backup_to_s3(triggered_by=triggered_by)
            except Exception:
                _log.warning("S3 backup failed (non-fatal)", exc_info=True)

    def _all_templates(self) -> dict[str, str]:
        """Return all templates as {stem: zpl_content}."""
        resp = self._table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": "TEMPLATE"},
        )
        return {item["SK"]: str(item["zpl_content"]) for item in resp.get("Items", [])}

    @staticmethod
    def _normalize_stem(name: str) -> str:
        """Normalize template name to a stem (strip .zpl if present)."""
        raw = str(name or "").strip()
        if not raw:
            raise ValueError("Template name cannot be empty")
        if "/" in raw or "\\" in raw:
            raise ValueError("Template name must be a simple filename (no directories)")
        if raw.endswith(".zpl"):
            raw = raw[:-4]
        if not raw:
            raise ValueError("Template name cannot be empty")
        return raw