#!/usr/bin/env python3
"""SYS-LINK-001 backup replication — v0.2 controlled operational baseline.

Default --plan is offline. --execute needs an allowlisted environment profile,
explicit reviewed configuration, three systemd-loaded credentials, a trusted
pinned AWS CLI, and private paths. No boto3 dependency, shell execution, key
provisioning or remote delete calls.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import dataclasses
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

VERSION = "0.2"
SYSTEM = "SYS-LINK-001"
R2_ENDPOINT = "https://8ec92aac91a6fd67882bcbe1f94d4d98.r2.cloudflarestorage.com"
R2_PREFIX = "backups/links-"
B2_ENDPOINT = "https://s3.us-west-004.backblazeb2.com"
B2_BUCKET = "onzko-automation-prod-backups"
AWS_PATH = "/usr/local/lib/onzko-link-backup/aws-cli/v2/current/bin/aws"
AWS_VERSION = "2.36.44"
DEFAULT_CONFIG = "/etc/onzko-link-backup/config.json"
SOURCE_RE = re.compile(r"backups/links-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z)\.json\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")

PROFILES = {
    "staging": {
        "r2_bucket": "onzko-link-stg-backups",
        "b2_prefix": "systems/sys-link-001/staging/",
        "state_path": Path("/var/lib/onzko-link-backup"),
        "work_path": Path("/run/onzko-link-backup"),
    },
    "production": {
        "r2_bucket": "onzko-link-prod-backups",
        "b2_prefix": "systems/sys-link-001/production/",
        "state_path": Path("/var/lib/onzko-link-prod-backup"),
        "work_path": Path("/run/onzko-link-prod-backup"),
    },
}

ACTIVE_PROFILE = "staging"
R2_BUCKET = PROFILES["staging"]["r2_bucket"]
B2_PREFIX = PROFILES["staging"]["b2_prefix"]
STATE_PATH = PROFILES["staging"]["state_path"]
WORK_PATH = PROFILES["staging"]["work_path"]
DEST_RE = re.compile(
    re.escape(B2_PREFIX)
    + r"snapshots/\d{8}T\d{6}\.\d{3}Z/[0-9a-f]{64}/(?:links|manifest)\.json\Z"
)


class BackupError(Exception):
    """Only fixed non-secret error codes may reach logs."""


def require(test: bool, code: str) -> None:
    if not test:
        raise BackupError(code)


def configure_profile(name: str) -> None:
    """Select one fixed environment identity; arbitrary storage targets are prohibited."""
    global ACTIVE_PROFILE, R2_BUCKET, B2_PREFIX, STATE_PATH, WORK_PATH, DEST_RE

    profile = PROFILES.get(name)
    require(profile is not None, "profile_not_allowed")

    ACTIVE_PROFILE = name
    R2_BUCKET = profile["r2_bucket"]
    B2_PREFIX = profile["b2_prefix"]
    STATE_PATH = profile["state_path"]
    WORK_PATH = profile["work_path"]
    DEST_RE = re.compile(
        re.escape(B2_PREFIX)
        + r"snapshots/\d{8}T\d{6}\.\d{3}Z/[0-9a-f]{64}/(?:links|manifest)\.json\Z"
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(raw: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "json_duplicate_member")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise BackupError("json_nonfinite_number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackupError("invalid_json") from None


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def text(value: Any, limit: int = 1024) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and all(32 <= ord(c) < 127 for c in value)


def version_id(value: Any) -> bool:
    return text(value) and value != "null" and not value.startswith("-")


def credential_acl_ok(raw: bytes, uid: int) -> bool:
    """Accept only systemd's root-owner + one service-UID read ACL (Linux format)."""
    if len(raw) < 4 or (len(raw) - 4) % 8 or struct.unpack_from("<I", raw)[0] != 2:
        return False
    entries = [struct.unpack_from("<HHI", raw, offset) for offset in range(4, len(raw), 8)]
    expected = {(1, 4, 0xFFFFFFFF), (2, 4, uid), (4, 0, 0xFFFFFFFF),
                (16, 4, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)}
    return len(entries) == len(expected) and set(entries) == expected


def read_private(path: Path, limit: int, *, systemd_credential: bool = False) -> bytes:
    """Private state, or a validated systemd read-only credential ACL; no symlinks."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "private_file_not_regular")
        owners = (0, os.geteuid()) if systemd_credential else (os.geteuid(),)
        require(info.st_uid in owners, "private_file_wrong_owner")
        if info.st_mode & 0o077:
            require(systemd_credential and info.st_mode & 0o077 == 0o040,
                    "private_file_insecure_mode")
            try:
                acl = os.getxattr(fd, "system.posix_acl_access")
            except (OSError, AttributeError):
                raise BackupError("credential_acl_missing") from None
            require(credential_acl_ok(acl, os.geteuid()), "credential_acl_not_private")
        require(info.st_size <= limit, "private_file_too_large")
        with os.fdopen(os.dup(fd), "rb") as stream:
            value = stream.read(limit + 1)
        require(len(value) <= limit, "private_file_too_large")
        return value
    finally:
        os.close(fd)


def private_directory(path: Path) -> None:
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not path.is_symlink(), "private_directory_invalid")
    require(info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0, "private_directory_permissions")


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_mode & 0o077 == 0, "lock_file_invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("run_already_active") from None
        yield
    finally:
        os.close(fd)


def atomic_json(path: Path, value: Any) -> None:
    """A success record is either old and complete, or new and complete."""
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclasses.dataclass(frozen=True)
class Policy:
    live_execution_approved: bool = False
    source_schedule_reviewed: bool = False
    aws_binary_sha256: str = ""
    expected_source_interval_seconds: int = 43200  # Reviewed 12-hour scheduled-source interval.
    source_completion_budget_seconds: int = 900
    poll_seconds: int = 900
    jitter_seconds: int = 120
    timer_accuracy_seconds: int = 60
    run_budget_seconds: int = 600
    max_source_age_seconds: int = 46800
    max_object_bytes: int = 16 * 1024 * 1024
    max_list_pages: int = 10
    max_snapshots: int = 120
    max_links: int = 100000

    @classmethod
    def load(cls, value: Any) -> "Policy":
        require(isinstance(value, dict), "policy_not_object")
        known = {f.name for f in dataclasses.fields(cls)}
        require(set(value) == known, "policy_fields_mismatch")
        for flag in ("live_execution_approved", "source_schedule_reviewed"):
            require(type(value[flag]) is bool, "policy_invalid_boolean")
        require(isinstance(value["aws_binary_sha256"], str), "policy_invalid_hash")
        for name in known - {"live_execution_approved", "source_schedule_reviewed", "aws_binary_sha256"}:
            require(type(value[name]) is int and value[name] > 0, "policy_invalid_integer")
        p = cls(**value)
        require(p.expected_source_interval_seconds <= 43200, "source_interval_exceeds_draft_budget")
        require(p.poll_seconds == 900 and p.jitter_seconds == 120 and p.timer_accuracy_seconds == 60,
                "timer_policy_mismatch")
        require(p.run_budget_seconds <= 600, "run_budget_exceeds_unit_budget")
        require(p.max_source_age_seconds <= 46800, "freshness_limit_too_weak")
        require(p.max_object_bytes <= 16 * 1024 * 1024 and p.max_list_pages <= 10
                and p.max_snapshots <= 120 and p.max_links <= 100000, "resource_limit_too_large")
        require(p.normal_age_budget() < 86400, "rpo_budget_exceeded")
        return p

    def normal_age_budget(self) -> int:
        return (self.expected_source_interval_seconds + self.source_completion_budget_seconds
                + self.poll_seconds + self.jitter_seconds + self.timer_accuracy_seconds
                + self.run_budget_seconds)

    def execution_gate(self) -> None:
        require(self.live_execution_approved, "live_execution_not_approved")
        require(self.source_schedule_reviewed, "source_schedule_not_reviewed")
        require(bool(HASH_RE.fullmatch(self.aws_binary_sha256)), "aws_binary_pin_missing")


@dataclasses.dataclass(frozen=True, repr=False)
class Credential:
    access_id: str
    secret: str

    def __repr__(self) -> str:
        return "Credential(REDACTED)"

    @classmethod
    def load(cls, path: Path, role: str) -> "Credential":
        data = strict_json(read_private(path, 8192, systemd_credential=True))
        require(isinstance(data, dict) and set(data) == {"accessKeyId", "secretAccessKey"},
                "credential_schema_invalid")
        kid, secret = data["accessKeyId"], data["secretAccessKey"]
        require(text(kid, 256) and text(secret, 1024), "credential_invalid_text")
        require(not any(c.isspace() for c in kid + secret), "credential_whitespace")
        require(len(kid) >= 16 and len(secret) >= 16, "credential_missing_or_placeholder")
        require("REPLACE" not in kid + secret and "EXAMPLE" not in kid + secret,
                "credential_placeholder")
        if role == "r2-reader":
            require(bool(re.fullmatch(r"[0-9a-fA-F]{32}", kid)), "r2_access_id_format")
            require(bool(re.fullmatch(r"[0-9a-fA-F]{64}", secret)), "r2_s3_secret_format")
        return cls(kid, secret)


def load_credentials(path: Path) -> dict[str, Credential]:
    credentials = {role: Credential.load(path / f"{role}.json", role)
                   for role in ("r2-reader", "b2-writer", "b2-reader")}
    require(credentials["b2-writer"].access_id != credentials["b2-reader"].access_id,
            "writer_reader_identity_not_separate")
    return credentials


def isolated_env(credential: Credential, region: str, home: Path) -> dict[str, str]:
    """Start empty; never inherit profiles, session tokens, proxies or other keys."""
    return {
        "PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "TMPDIR": str(home), "AWS_ACCESS_KEY_ID": credential.access_id,
        "AWS_SECRET_ACCESS_KEY": credential.secret, "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region, "AWS_CONFIG_FILE": "/dev/null",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", "BOTO_CONFIG": "/dev/null",
        "AWS_EC2_METADATA_DISABLED": "true", "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
        "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off", "AWS_RETRY_MODE": "standard",
        "AWS_MAX_ATTEMPTS": "3", "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
        "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
    }


def trusted_root_path(path: Path) -> None:
    """Both symlink chain locations and resolved ancestors must be root controlled."""
    require(path.is_absolute(), "trusted_path_not_absolute")
    for start in (path, path.resolve(strict=True)):
        for part in (start, *start.parents):
            info = part.lstat()
            require(info.st_uid == 0, "trusted_path_not_root_owned")
            if not stat.S_ISLNK(info.st_mode):
                require(info.st_mode & 0o022 == 0, "trusted_path_writable_by_others")


class AwsGateway:
    """The sole AWS subprocess boundary. No generic arbitrary operation passthrough."""
    ALLOWED = {
        "r2-reader": frozenset({"list-objects-v2", "get-object"}),
        "b2-writer": frozenset({"put-object"}),
        "b2-reader": frozenset({"get-object"}),
    }

    def __init__(self, credentials: dict[str, Credential], home: Path, deadline: float,
                 runner: Callable[..., Any] = subprocess.run):
        self.credentials, self.home, self.deadline, self.runner = credentials, home, deadline, runner

    def call(self, role: str, operation: str, *, key: str | None = None,
             prefix: str | None = None, continuation: str | None = None,
             output: Path | None = None, body: Path | None = None,
             etag: str | None = None, version: str | None = None) -> dict[str, Any]:
        require(operation in self.ALLOWED.get(role, ()), "operation_not_allowed")
        require(role in self.credentials, "role_credential_missing")
        is_r2 = role == "r2-reader"
        endpoint, bucket, region = ((R2_ENDPOINT, R2_BUCKET, "auto") if is_r2
                                    else (B2_ENDPOINT, B2_BUCKET, "us-west-004"))
        args = [AWS_PATH, "--endpoint-url", endpoint, "--region", region, "--output", "json",
                "--no-cli-pager", "--no-cli-auto-prompt", "--color", "off", "--no-paginate",
                "--cli-connect-timeout", "10", "--cli-read-timeout", "60", "s3api", operation,
                "--bucket", bucket]
        if operation == "list-objects-v2":
            require(is_r2 and prefix == R2_PREFIX, "listing_prefix_not_allowed")
            require(key is None and output is None and body is None, "invalid_list_arguments")
            args += ["--prefix", prefix, "--max-keys", "1000"]
            if continuation is not None:
                require(text(continuation, 8192) and not continuation.startswith("-"), "bad_continuation")
                args += ["--continuation-token", continuation]
        else:
            require(isinstance(key, str) and bool((SOURCE_RE if is_r2 else DEST_RE).fullmatch(key)),
                    "object_key_not_allowed")
            args += ["--key", key]
            if operation == "get-object":
                require(output is not None and body is None, "invalid_get_arguments")
                if is_r2:
                    require(text(etag, 256) and version is None, "r2_conditional_get_required")
                    args += ["--if-match", etag]
                else:
                    require(version_id(version), "b2_exact_version_required")
                    args += ["--version-id", version]
                args += [str(output)]
            elif operation == "put-object":
                require(body is not None and output is None and version is None, "invalid_put_arguments")
                raw = body.read_bytes()
                # MD5 is transport validation, NOT the recorded recovery fingerprint.
                content_md5 = base64.b64encode(hashlib.md5(raw, usedforsecurity=False).digest()).decode()
                args += ["--body", str(body), "--content-type", "application/json", "--content-md5", content_md5]
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "run_deadline_exceeded")
        try:
            result = self.runner(args, env=isolated_env(self.credentials[role], region, self.home),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=min(120, remaining), check=False)
        except subprocess.TimeoutExpired:
            raise BackupError("aws_operation_timeout") from None
        # Never print stderr/stdout on failure: diagnostic bodies may contain sensitive material.
        require(result.returncode == 0, "aws_operation_failed")
        value = strict_json(result.stdout)
        require(isinstance(value, dict), "aws_response_not_object")
        return value


def source_time(key: str) -> datetime:
    match = SOURCE_RE.fullmatch(key)
    require(match is not None, "invalid_source_name")
    try:
        return datetime.strptime(match[1], "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise BackupError("invalid_source_timestamp") from None


@dataclasses.dataclass(frozen=True)
class Snapshot:
    key: str
    size: int
    etag: str
    exported: datetime


def enumerate_sources(gateway: AwsGateway, policy: Policy, now: datetime) -> list[Snapshot]:
    snapshots: dict[str, Snapshot] = {}
    seen_tokens: set[str] = set()
    continuation: str | None = None
    for _ in range(policy.max_list_pages):
        page = gateway.call("r2-reader", "list-objects-v2", prefix=R2_PREFIX, continuation=continuation)
        objects = page.get("Contents", [])
        require(isinstance(objects, list), "listing_contents_invalid")
        for obj in objects:
            require(isinstance(obj, dict) and isinstance(obj.get("Key"), str), "listing_entry_invalid")
            key = obj["Key"]
            require(key.startswith(R2_PREFIX), "source_outside_listing_prefix")
            if not SOURCE_RE.fullmatch(key):
                # In-progress application uploads are not complete backups.
                require(".json.pending-" in key, "unrecognised_scheduled_object")
                continue
            size, etag = obj.get("Size"), obj.get("ETag")
            require(type(size) is int and 0 < size <= policy.max_object_bytes, "source_size_out_of_bounds")
            require(text(etag, 256) and not etag.startswith("-"), "source_etag_missing")
            exported = source_time(key)
            require((exported - now).total_seconds() <= 300, "source_timestamp_in_future")
            require(key not in snapshots, "source_duplicate_listing_key")
            snapshots[key] = Snapshot(key, size, etag, exported)
            require(len(snapshots) <= policy.max_snapshots, "source_backlog_limit_exceeded")
        truncated = page.get("IsTruncated", False)
        require(type(truncated) is bool, "listing_truncation_invalid")
        if not truncated:
            break
        continuation = page.get("NextContinuationToken")
        require(text(continuation, 8192) and continuation not in seen_tokens, "pagination_invalid")
        seen_tokens.add(continuation)
    else:
        raise BackupError("pagination_limit_exceeded")
    require(bool(snapshots), "no_complete_scheduled_snapshot")
    ordered = sorted(snapshots.values(), key=lambda item: (item.exported, item.key), reverse=True)
    require((now - ordered[0].exported).total_seconds() <= policy.max_source_age_seconds,
            "latest_scheduled_snapshot_stale")
    return ordered


def validate_backup(raw: bytes, snapshot: Snapshot, policy: Policy, now: datetime) -> dict[str, Any]:
    require(len(raw) == snapshot.size and len(raw) <= policy.max_object_bytes, "source_length_mismatch")
    data = strict_json(raw)
    require(isinstance(data, dict) and data.get("version") == "1.0", "backup_version_invalid")
    exported = data.get("exportedAt")
    require(isinstance(exported, str) and exported == stamp(snapshot.exported), "backup_timestamp_mismatch")
    require((snapshot.exported - now).total_seconds() <= 300, "backup_future_timestamp")
    count, links = data.get("count"), data.get("links")
    require(type(count) is int and 0 <= count <= policy.max_links, "backup_count_invalid")
    require(isinstance(links, list) and len(links) == count, "backup_count_mismatch")
    slugs, ids = set(), set()
    for link in links:
        require(isinstance(link, dict), "backup_link_not_object")
        slug, kid, url = link.get("slug"), link.get("id"), link.get("url")
        require(isinstance(slug, str) and 0 < len(slug) <= 1024 and
                all(ord(c) >= 32 and ord(c) != 127 for c in slug), "backup_slug_invalid")
        require(text(kid, 256) and kid not in ids and slug not in slugs, "backup_duplicate_or_bad_identity")
        require(isinstance(url, str) and len(url) <= 16384, "backup_url_invalid")
        try:
            parts = urlsplit(url)
            require(parts.scheme in ("https", "http") and bool(parts.hostname), "backup_url_invalid")
        except ValueError:
            raise BackupError("backup_url_invalid") from None
        tags = link.get("tags", [])
        require(isinstance(tags, list) and all(isinstance(tag, str) for tag in tags), "backup_tags_invalid")
        slugs.add(slug)
        ids.add(kid)
    # Original bytes (including all optional fields) are copied, not reconstructed.
    return {"sha256": digest(raw), "count": count, "exportedAt": exported, "bytes": len(raw)}


def destination_base(snapshot: Snapshot, sha256: str) -> str:
    require(bool(HASH_RE.fullmatch(sha256)), "invalid_sha256")
    token = snapshot.exported.strftime("%Y%m%dT%H%M%S.") + f"{snapshot.exported.microsecond // 1000:03d}Z"
    return f"{B2_PREFIX}snapshots/{token}/{sha256}/"


def download_exact(gateway: AwsGateway, key: str, vid: str, output: Path, expected_sha: str,
                   expected_size: int) -> None:
    meta = gateway.call("b2-reader", "get-object", key=key, version=vid, output=output)
    require(meta.get("VersionId") == vid, "b2_returned_version_mismatch")
    require(output.stat().st_size == expected_size, "b2_readback_mismatch")
    raw = output.read_bytes()
    require(len(raw) == expected_size and digest(raw) == expected_sha, "b2_readback_mismatch")


def receipt_path(state: Path, snapshot: Snapshot) -> Path:
    return state / (hashlib.sha256(snapshot.key.encode()).hexdigest() + ".json")


def replicate_snapshot(gateway: AwsGateway, policy: Policy, snapshot: Snapshot, state: Path,
                       work: Path, now: datetime, verify_existing: bool) -> dict[str, Any]:
    record_path = receipt_path(state, snapshot)
    record = None
    if record_path.exists():
        record = strict_json(read_private(record_path, 65536))
        require(isinstance(record, dict), "receipt_invalid")
        require(record.get("source_key") == snapshot.key and record.get("source_etag") == snapshot.etag
                and record.get("bytes") == snapshot.size, "source_changed_since_receipt")
        require(isinstance(record.get("sha256"), str) and bool(HASH_RE.fullmatch(record["sha256"])),
                "receipt_hash_invalid")
        expected_base = destination_base(snapshot, record["sha256"])
        require(record.get("data_key") == expected_base + "links.json"
                and record.get("manifest_key") == expected_base + "manifest.json", "receipt_scope_invalid")
        require(record.get("exportedAt") == stamp(snapshot.exported), "receipt_timestamp_invalid")
        require(type(record.get("count")) is int and record["count"] >= 0, "receipt_count_invalid")
        require(record.get("status") in ("uploaded", "data_verified", "manifest_uploaded", "verified"),
                "receipt_status_invalid")
        require(version_id(record.get("data_version_id")), "receipt_version_invalid")
        if record.get("status") == "verified":
            require(version_id(record.get("manifest_version_id"))
                    and bool(HASH_RE.fullmatch(record.get("manifest_sha256", ""))), "receipt_manifest_invalid")
            if not verify_existing:
                return record
    with tempfile.TemporaryDirectory(prefix="object-", dir=work) as temporary:
        scratch = Path(temporary)
        if record is None:
            source_file = scratch / "source.json"
            metadata = gateway.call("r2-reader", "get-object", key=snapshot.key,
                                    etag=snapshot.etag, output=source_file)
            require(metadata.get("ETag") == snapshot.etag, "source_changed_during_download")
            require(source_file.stat().st_size == snapshot.size, "source_length_mismatch")
            info = validate_backup(source_file.read_bytes(), snapshot, policy, now)
            base = destination_base(snapshot, info["sha256"])
            result = gateway.call("b2-writer", "put-object", key=base + "links.json", body=source_file)
            vid = result.get("VersionId")
            require(version_id(vid), "put_response_version_missing")
            record = {"system": SYSTEM, "source_key": snapshot.key, "source_etag": snapshot.etag,
                      **info, "data_key": base + "links.json", "data_version_id": vid,
                      "manifest_key": base + "manifest.json", "status": "uploaded"}
            atomic_json(record_path, record)
        download_exact(gateway, record["data_key"], record["data_version_id"], scratch / "readback.json",
                       record["sha256"], record["bytes"])
        if record["status"] != "verified":
            record["status"] = "data_verified"
            atomic_json(record_path, record)
        manifest = {
            "format": "sys-link-001-replication-manifest-v1", "system": SYSTEM,
            "status": "data_version_readback_verified", "source_bucket": R2_BUCKET,
            "source_key": snapshot.key, "source_etag": snapshot.etag,
            "exportedAt": record["exportedAt"], "bytes": record["bytes"], "count": record["count"],
            "sha256": record["sha256"], "destination_bucket": B2_BUCKET,
            "data_key": record["data_key"], "data_version_id": record["data_version_id"],
            "object_lock_verification": "separate_audit_required",
        }
        manifest_raw = json_bytes(manifest)
        manifest_sha = digest(manifest_raw)
        if record.get("manifest_version_id"):
            require(record.get("manifest_sha256") == manifest_sha, "receipt_manifest_content_mismatch")
        else:
            manifest_file = scratch / "manifest.json"
            manifest_file.write_bytes(manifest_raw)
            put = gateway.call("b2-writer", "put-object", key=record["manifest_key"], body=manifest_file)
            require(version_id(put.get("VersionId")), "manifest_version_missing")
            record.update(manifest_version_id=put["VersionId"], manifest_sha256=manifest_sha,
                          status="manifest_uploaded")
            atomic_json(record_path, record)
        download_exact(gateway, record["manifest_key"], record["manifest_version_id"],
                       scratch / "manifest-readback.json", manifest_sha, len(manifest_raw))
        record.update(status="verified", last_verified_at=stamp(utcnow()))
        atomic_json(record_path, record)
        return record


def perform_run(gateway: AwsGateway, policy: Policy, state: Path, work: Path,
                clock: Callable[[], datetime] = utcnow) -> dict[str, Any]:
    """Caller owns lock. Partial object receipts survive failure; no false run success."""
    began = clock()
    try:
        snapshots = enumerate_sources(gateway, policy, began)
        newest = None
        for index, snapshot in enumerate(snapshots):
            require(time.monotonic() < gateway.deadline, "run_deadline_exceeded")
            record = replicate_snapshot(gateway, policy, snapshot, state, work, began, verify_existing=index == 0)
            if index == 0:
                newest = record
        ended = clock()
        age = max(0, (ended - snapshots[0].exported).total_seconds())
        require(age <= policy.max_source_age_seconds, "recovery_point_stale_at_completion")
        result = {"system": SYSTEM, "status": "verified", "started_at": stamp(began),
                  "finished_at": stamp(ended), "snapshot_count": len(snapshots),
                  "latest_source_exported_at": newest["exportedAt"], "latest_source_age_seconds": int(age),
                  "latest_data_key": newest["data_key"], "latest_data_version_id": newest["data_version_id"],
                  "latest_sha256": newest["sha256"], "normal_age_budget_seconds": policy.normal_age_budget(),
                  "rpo_guaranteed": False, "object_lock_audit": "not_performed_by_runtime_job"}
        atomic_json(state / "last_success.json", result)
        atomic_json(state / "last_attempt.json", result)
        return result
    except BackupError as exc:
        atomic_json(state / "last_attempt.json", {"system": SYSTEM, "status": "failed", "code": str(exc),
                                                 "attempted_at": stamp(clock())})
        raise


def offline_plan(policy: Policy) -> dict[str, Any]:
    return {"system": SYSTEM, "profile": ACTIVE_PROFILE,
            "draft_version": VERSION, "mode": "OFFLINE_PLAN",
            "network_calls": 0, "credentials_loaded": False, "installation_authorised": False,
            "source": {"endpoint": R2_ENDPOINT, "bucket": R2_BUCKET, "prefix": R2_PREFIX},
            "destination": {"endpoint": B2_ENDPOINT, "bucket": B2_BUCKET, "prefix": B2_PREFIX},
            "writer_capabilities": ["writeFiles"], "reader_capabilities": ["listFiles", "readFiles"],
            "runtime_calls": {role: sorted(ops) for role, ops in AwsGateway.ALLOWED.items()},
            "proposed_normal_age_budget_seconds": policy.normal_age_budget(),
            "live_execution_approved": policy.live_execution_approved,
            "source_schedule_reviewed": policy.source_schedule_reviewed,
            "aws_binary_pin_present": bool(HASH_RE.fullmatch(policy.aws_binary_sha256))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default="staging")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--plan", action="store_true", help="Offline; default. No credential or cloud access.")
    modes.add_argument("--execute", action="store_true", help="Requires separately reviewed live configuration.")
    args = parser.parse_args(argv)
    try:
        configure_profile(args.profile)
        path = Path(args.config)
        if args.execute:
            trusted_root_path(path)
        require(path.stat().st_size <= 16384, "policy_too_large")
        policy = Policy.load(strict_json(path.read_bytes()))
        if not args.execute:
            print(json.dumps(offline_plan(policy), indent=2))
            return 0
        policy.execution_gate()  # Before any credentials or external process.
        os.umask(0o077)
        require(os.geteuid() != 0, "run_as_dedicated_unprivileged_user")
        private_directory(STATE_PATH)
        private_directory(WORK_PATH)
        trusted_root_path(Path(AWS_PATH))
        require(digest(Path(AWS_PATH).read_bytes()) == policy.aws_binary_sha256, "aws_binary_pin_mismatch")
        credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "")
        require(bool(credential_dir) and Path(credential_dir).is_absolute(), "systemd_credentials_missing")
        credentials = load_credentials(Path(credential_dir))
        with exclusive_lock(STATE_PATH / "run.lock"):
            with tempfile.TemporaryDirectory(prefix="run-", dir=WORK_PATH) as temporary:
                scratch = Path(temporary)
                env = isolated_env(credentials["r2-reader"], "auto", scratch)
                checked = subprocess.run([AWS_PATH, "--version"], env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
                require(checked.returncode == 0 and checked.stdout.startswith(f"aws-cli/{AWS_VERSION} ".encode()),
                        "aws_cli_version_mismatch")
                gateway = AwsGateway(credentials, scratch, time.monotonic() + policy.run_budget_seconds)
                result = perform_run(gateway, policy, STATE_PATH, scratch)
                print(json.dumps(result, sort_keys=True))
        return 0
    except BackupError as exc:
        print(json.dumps({"system": SYSTEM, "status": "failed", "code": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"system": SYSTEM, "status": "failed", "code": "local_dependency_failure"}), file=sys.stderr)
        return 1
    except Exception:
        # Suppress unexpected tracebacks containing untrusted data or process arguments.
        print(json.dumps({"system": SYSTEM, "status": "failed", "code": "unexpected_failure"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
