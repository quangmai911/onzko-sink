"""Offline tests: fake AWS subprocess boundary, synthetic credentials, no network."""
import base64
import contextlib
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("linkbackup", ROOT / "src" / "onzko_link_backup.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
NOW = datetime(2026, 9, 27, 13, 0, tzinfo=timezone.utc)
KEY = "backups/links-2026-09-27T12-00-00.000Z.json"
OLD_KEY = "backups/links-2026-09-26T12-00-00.000Z.json"
CREDS = {
    "r2-reader": m.Credential("a" * 32, "b" * 64),
    "b2-writer": m.Credential("OFFLINE_WRITER_ID_ONLY", "OFFLINE_WRITER_SECRET_ONLY"),
    "b2-reader": m.Credential("OFFLINE_READER_ID_ONLY", "OFFLINE_READER_SECRET_ONLY"),
}


def backup(key=KEY, count=1):
    return m.json_bytes({"version": "1.0", "exportedAt": m.stamp(m.source_time(key)), "count": count,
        "links": [{"id": "test-id-1", "slug": "offline-test", "url": "https://example.com/", "tags": [],
                   "password": "OFFLINE_NOT_A_REAL_PASSWORD_HASH"}] if count else []})


class FakeAWS:
    """Checks routing and represents objects as versioned bytes in memory."""
    def __init__(self):
        self.source = {KEY: backup()}
        self.pages = None
        self.objects = {}
        self.calls = []
        self.counter = 0
        self.fail_operation = None
        self.bad_readback = False
        self.bad_version = False
        self.missing_put_version = False
        self.fail_manifest_get_once = False

    def __call__(self, args, **kwargs):
        env = kwargs["env"]
        operation = args[args.index("s3api") + 1]
        role = next(role for role, c in CREDS.items() if c.access_id == env["AWS_ACCESS_KEY_ID"])
        self.calls.append((role, operation, list(args), dict(env)))
        assert operation in m.AwsGateway.ALLOWED[role]
        assert env["AWS_SECRET_ACCESS_KEY"] == CREDS[role].secret
        assert "AWS_SESSION_TOKEN" not in env and "AWS_PROFILE" not in env
        assert "HTTP_PROXY" not in env and "AWS_ENDPOINT_URL" not in env
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs
        assert "--no-paginate" in args
        def option(flag):
            return args[args.index(flag) + 1]
        expected_endpoint = m.R2_ENDPOINT if role == "r2-reader" else m.B2_ENDPOINT
        assert option("--endpoint-url") == expected_endpoint
        assert option("--bucket") == (m.R2_BUCKET if role == "r2-reader" else m.B2_BUCKET)
        if self.fail_operation == (role, operation):
            return subprocess.CompletedProcess(args, 9, b"", b"SECRET_MUST_NOT_APPEAR")
        if operation == "list-objects-v2":
            assert option("--prefix") == m.R2_PREFIX
            if self.pages is not None:
                page = int(option("--continuation-token")) if "--continuation-token" in args else 0
                result = self.pages[page]
            else:
                result = {"Contents": [{"Key": key, "Size": len(raw), "ETag": '"source-etag"'}
                                       for key, raw in self.source.items()], "IsTruncated": False}
        elif role == "r2-reader":
            key = option("--key")
            assert option("--if-match") == '"source-etag"'
            Path(args[-1]).write_bytes(self.source[key])
            result = {"ETag": '"source-etag"', "ContentLength": len(self.source[key])}
        elif operation == "put-object":
            key = option("--key")
            assert key.startswith(m.B2_PREFIX)
            raw = Path(option("--body")).read_bytes()
            assert option("--content-md5") == base64.b64encode(hashlib.md5(raw).digest()).decode()
            self.counter += 1
            vid = f"offline-version-{self.counter}"
            self.objects[(key, vid)] = raw
            result = {} if self.missing_put_version else {"VersionId": vid, "ETag": '"not-sha256"'}
        else:
            key, vid = option("--key"), option("--version-id")
            if self.fail_manifest_get_once and key.endswith("manifest.json"):
                self.fail_manifest_get_once = False
                return subprocess.CompletedProcess(args, 2, b"", b"intentional failure")
            raw = self.objects[(key, vid)]
            Path(args[-1]).write_bytes(raw + b"x" if self.bad_readback else raw)
            result = {"VersionId": "wrong" if self.bad_version else vid, "ContentLength": len(raw)}
        return subprocess.CompletedProcess(args, 0, json.dumps(result).encode(), b"")


class ReplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.state, self.work = self.path / "state", self.path / "work"
        self.state.mkdir(mode=0o700)
        self.work.mkdir(mode=0o700)
        self.policy = m.Policy()
        self.fake = FakeAWS()
        self.gateway = m.AwsGateway(CREDS, self.work, time.monotonic() + 600, runner=self.fake)
        self.no_network = patch.object(socket, "socket", side_effect=AssertionError("NETWORK_FORBIDDEN"))
        self.no_network.start()

    def tearDown(self):
        self.no_network.stop()
        self.tmp.cleanup()

    def run_job(self):
        return m.perform_run(self.gateway, self.policy, self.state, self.work, clock=lambda: NOW)

    def snapshot(self, raw=None, key=KEY):
        raw = raw or backup(key)
        return m.Snapshot(key, len(raw), '"source-etag"', m.source_time(key))

    def assert_fails(self, code):
        with self.assertRaisesRegex(m.BackupError, code):
            self.run_job()
        self.assertFalse((self.state / "last_success.json").exists())

    def test_nonempty_roundtrip_exact_version_and_manifest(self):
        result = self.run_job()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["latest_sha256"], m.digest(backup()))
        self.assertFalse(result["rpo_guaranteed"])
        self.assertEqual([(r, o) for r, o, _, _ in self.fake.calls], [
            ("r2-reader", "list-objects-v2"), ("r2-reader", "get-object"),
            ("b2-writer", "put-object"), ("b2-reader", "get-object"),
            ("b2-writer", "put-object"), ("b2-reader", "get-object")])
        self.assertEqual(len(list(self.work.iterdir())), 0)

    def test_empty_scheduled_backup_is_structurally_valid(self):
        self.fake.source[KEY] = backup(count=0)
        self.assertEqual(self.run_job()["status"], "verified")

    def test_no_scheduled_object_stops_without_put(self):
        self.fake.source.clear()
        self.assert_fails("no_complete_scheduled_snapshot")
        self.assertEqual(len(self.fake.calls), 1)

    def test_pending_object_not_treated_as_backup(self):
        self.fake.source = {KEY + ".pending-offline": b"incomplete"}
        self.assert_fails("no_complete_scheduled_snapshot")

    def test_manual_object_in_scheduled_listing_is_rejected(self):
        self.fake.source = {"backups/manual-links-2026-09-27T12-00-00.000Z.json": b"{}"}
        self.assert_fails("source_outside_listing_prefix")

    def test_stale_newest_stops_all_uploads(self):
        self.fake.source = {OLD_KEY: backup(OLD_KEY)}
        self.assert_fails("latest_scheduled_snapshot_stale")
        self.assertEqual(self.fake.counter, 0)

    def test_future_source_rejected(self):
        key = "backups/links-2026-09-28T12-00-00.000Z.json"
        self.fake.source = {key: backup(key)}
        self.assert_fails("source_timestamp_in_future")

    def test_count_mismatch_rejected(self):
        data = json.loads(backup()); data["count"] = 0
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_count_mismatch")

    def test_boolean_count_rejected(self):
        data = json.loads(backup()); data["count"] = True
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_count_invalid")

    def test_duplicate_json_fields_rejected(self):
        self.fake.source[KEY] = b'{"version":"1.0","version":"1.0"}'
        self.assert_fails("json_duplicate_member")

    def test_nan_rejected(self):
        self.fake.source[KEY] = b'{"version":"1.0","count":NaN}'
        self.assert_fails("json_nonfinite_number")

    def test_backup_version_rejected(self):
        data = json.loads(backup()); data["version"] = "2.0"
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_version_invalid")

    def test_timestamp_content_mismatch_rejected(self):
        data = json.loads(backup()); data["exportedAt"] = "2026-09-27T11:00:00.000Z"
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_timestamp_mismatch")

    def test_duplicate_link_identity_rejected(self):
        data = json.loads(backup()); data["links"] *= 2; data["count"] = 2
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_duplicate_or_bad_identity")

    def test_bad_url_rejected(self):
        data = json.loads(backup()); data["links"][0]["url"] = "file:///etc/passwd"
        self.fake.source[KEY] = m.json_bytes(data)
        self.assert_fails("backup_url_invalid")

    def test_length_mismatch_rejected(self):
        self.fake.pages = [{"Contents": [{"Key": KEY, "Size": 1, "ETag": '"source-etag"'}]}]
        self.assert_fails("source_length_mismatch")

    def test_size_limit_checked_before_get(self):
        self.fake.pages = [{"Contents": [{"Key": KEY, "Size": 17000000, "ETag": '"source-etag"'}]}]
        self.assert_fails("source_size_out_of_bounds")
        self.assertEqual(len(self.fake.calls), 1)

    def test_pagination_used_and_all_snapshots_replicated(self):
        self.fake.source[OLD_KEY] = backup(OLD_KEY)
        def item(key): return {"Key": key, "Size": len(self.fake.source[key]), "ETag": '"source-etag"'}
        self.fake.pages = [{"Contents": [item(OLD_KEY)], "IsTruncated": True, "NextContinuationToken": "1"},
                           {"Contents": [item(KEY)], "IsTruncated": False}]
        self.assertEqual(self.run_job()["snapshot_count"], 2)
        self.assertEqual(self.fake.counter, 4)

    def test_pagination_loop_rejected(self):
        self.fake.pages = [{"Contents": [], "IsTruncated": True, "NextContinuationToken": "0"}]
        self.assert_fails("pagination_invalid")

    def test_operation_allowlist_rejects_unauthorised_combinations(self):
        for role, operation in [("b2-writer", "get-object"), ("b2-writer", "delete-object"),
                                ("b2-reader", "put-object"), ("b2-reader", "list-buckets"),
                                ("r2-reader", "put-object"), ("r2-reader", "head-bucket")]:
            with self.subTest(role=role, operation=operation), self.assertRaises(m.BackupError):
                self.gateway.call(role, operation)
        self.assertFalse(self.fake.calls)

    def test_destination_prefix_escape_rejected(self):
        with self.assertRaisesRegex(m.BackupError, "object_key_not_allowed"):
            self.gateway.call("b2-writer", "put-object", key="production/test.json", body=self.path / "none")
        self.assertFalse(self.fake.calls)

    def test_reader_requires_specific_version(self):
        key = m.destination_base(self.snapshot(), "a" * 64) + "links.json"
        with self.assertRaisesRegex(m.BackupError, "b2_exact_version_required"):
            self.gateway.call("b2-reader", "get-object", key=key, output=self.work / "x")

    def test_source_get_requires_if_match(self):
        with self.assertRaisesRegex(m.BackupError, "r2_conditional_get_required"):
            self.gateway.call("r2-reader", "get-object", key=KEY, output=self.work / "x")

    def test_put_failure_never_marks_success(self):
        self.fake.fail_operation = ("b2-writer", "put-object")
        self.assert_fails("aws_operation_failed")
        self.assertNotIn("SECRET", (self.state / "last_attempt.json").read_text())

    def test_missing_version_id_never_marks_success(self):
        self.fake.missing_put_version = True
        self.assert_fails("put_response_version_missing")

    def test_corrupt_readback_fails(self):
        self.fake.bad_readback = True
        self.assert_fails("b2_readback_mismatch")

    def test_wrong_returned_version_fails(self):
        self.fake.bad_version = True
        self.assert_fails("b2_returned_version_mismatch")

    def test_rerun_rechecks_latest_versions_without_reupload(self):
        self.run_job(); count = self.fake.counter; before = len(self.fake.calls)
        self.run_job()
        self.assertEqual(self.fake.counter, count)
        self.assertEqual([(r, o) for r, o, _, _ in self.fake.calls[before:]], [
            ("r2-reader", "list-objects-v2"), ("b2-reader", "get-object"), ("b2-reader", "get-object")])

    def test_failed_manifest_verification_resumes_existing_versions(self):
        self.fake.fail_manifest_get_once = True
        self.assert_fails("aws_operation_failed")
        self.assertEqual(self.fake.counter, 2)
        self.assertEqual(self.run_job()["status"], "verified")
        self.assertEqual(self.fake.counter, 2)

    def test_failure_preserves_previous_success_not_new_false_success(self):
        self.run_job(); original = (self.state / "last_success.json").read_bytes()
        self.fake.fail_operation = ("b2-reader", "get-object")
        with self.assertRaises(m.BackupError): self.run_job()
        self.assertEqual((self.state / "last_success.json").read_bytes(), original)
        self.assertEqual(json.loads((self.state / "last_attempt.json").read_bytes())["status"], "failed")

    def test_tampered_receipt_cannot_change_destination(self):
        self.run_job()
        path = m.receipt_path(self.state, self.snapshot())
        data = json.loads(path.read_bytes()); data["data_key"] = "outside/test.json"
        m.atomic_json(path, data)
        before = len(self.fake.calls)
        with self.assertRaisesRegex(m.BackupError, "receipt_scope_invalid"): self.run_job()
        self.assertEqual(len(self.fake.calls), before + 1)

    def test_identity_contamination_not_inherited(self):
        with patch.dict(os.environ, {"AWS_SESSION_TOKEN": "fake", "AWS_PROFILE": "other",
                                   "AWS_ENDPOINT_URL": "https://elsewhere.invalid", "HTTP_PROXY": "bad",
                                   "OTHER_SYSTEM_SECRET": "do-not-inherit"}):
            env = m.isolated_env(CREDS["b2-writer"], "us-west-004", self.work)
        for name in ("AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_ENDPOINT_URL", "HTTP_PROXY", "OTHER_SYSTEM_SECRET"):
            self.assertNotIn(name, env)
        self.assertEqual(env["AWS_CONFIG_FILE"], "/dev/null")
        self.assertEqual(env["AWS_SHARED_CREDENTIALS_FILE"], "/dev/null")
        self.assertEqual(env["AWS_EC2_METADATA_DISABLED"], "true")

    def test_credential_repr_redacted(self):
        self.assertNotIn(CREDS["b2-writer"].secret, repr(CREDS["b2-writer"]))

    def test_credential_file_permissions_rejected(self):
        p = self.path / "creds.json"; p.write_text('{"accessKeyId":"x","secretAccessKey":"y"}'); p.chmod(0o644)
        with self.assertRaisesRegex(m.BackupError, "private_file_insecure_mode"):
            m.Credential.load(p, "r2-reader")

    def test_credential_symlink_rejected(self):
        p = self.path / "symlink"; p.symlink_to(self.path / "anything")
        with self.assertRaises(OSError): m.Credential.load(p, "b2-reader")

    def test_wrong_r2_secret_format_rejected(self):
        p = self.path / "creds.json"
        p.write_text(json.dumps({"accessKeyId": "a" * 32, "secretAccessKey": "cfat_" + "b" * 48})); p.chmod(0o600)
        with self.assertRaisesRegex(m.BackupError, "r2_s3_secret_format"): m.Credential.load(p, "r2-reader")

    def test_no_live_approval_default(self):
        with self.assertRaisesRegex(m.BackupError, "live_execution_not_approved"): self.policy.execution_gate()

    def test_source_schedule_requires_review(self):
        p = m.dataclasses.replace(self.policy, live_execution_approved=True)
        with self.assertRaisesRegex(m.BackupError, "source_schedule_not_reviewed"): p.execution_gate()

    def test_binary_pin_required(self):
        p = m.dataclasses.replace(self.policy, live_execution_approved=True, source_schedule_reviewed=True)
        with self.assertRaisesRegex(m.BackupError, "aws_binary_pin_missing"): p.execution_gate()

    def test_24_hour_source_interval_not_approved(self):
        value = m.dataclasses.asdict(self.policy); value["expected_source_interval_seconds"] = 86400
        with self.assertRaisesRegex(m.BackupError, "source_interval_exceeds_draft_budget"): m.Policy.load(value)

    def test_policy_cannot_override_bucket_or_endpoint(self):
        value = m.dataclasses.asdict(self.policy); value["bucket"] = "other"
        with self.assertRaisesRegex(m.BackupError, "policy_fields_mismatch"): m.Policy.load(value)

    def test_offline_plan_runs_without_credentials_or_aws(self):
        config = self.path / "config.json"; config.write_bytes(m.json_bytes(m.dataclasses.asdict(self.policy)))
        with patch.object(subprocess, "run", side_effect=AssertionError("NO_SUBPROCESS")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(m.main(["--config", str(config), "--plan"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["network_calls"], 0)
        self.assertFalse(result["credentials_loaded"])

    def test_deadline_stops_before_operation(self):
        self.gateway.deadline = time.monotonic() - 1
        self.assert_fails("run_deadline_exceeded")
        self.assertFalse(self.fake.calls)

    def test_subprocess_timeout_sanitised(self):
        def fail(*args, **kw): raise subprocess.TimeoutExpired("SENSITIVE", 1)
        self.gateway.runner = fail
        self.assert_fails("aws_operation_timeout")

    def test_atomic_receipts_private_and_no_temp_files(self):
        self.run_job()
        for p in self.state.glob("*.json"):
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(CREDS["b2-writer"].secret, p.read_text())
        self.assertFalse(list(self.state.glob(".state-*")))

    def test_binary_content_optional_fields_preserved(self):
        self.run_job()
        data_copies = [raw for (key, _), raw in self.fake.objects.items() if key.endswith("links.json")]
        self.assertEqual(data_copies, [backup()])


    def test_exclusive_lock_rejects_overlap(self):
        with m.exclusive_lock(self.state / "run.lock"):
            with self.assertRaisesRegex(m.BackupError, "run_already_active"):
                with m.exclusive_lock(self.state / "run.lock"):
                    self.fail("second lock must fail")

    def test_lock_released_after_failure(self):
        with self.assertRaises(RuntimeError):
            with m.exclusive_lock(self.state / "run.lock"):
                raise RuntimeError("offline")
        with m.exclusive_lock(self.state / "run.lock"):
            pass

    def test_lock_symlink_rejected(self):
        (self.state / "run.lock").symlink_to(self.path / "other")
        with self.assertRaises(OSError):
            with m.exclusive_lock(self.state / "run.lock"):
                self.fail("symlink lock must fail")

    def test_private_directory_rejects_group_access(self):
        self.work.chmod(0o750)
        with self.assertRaisesRegex(m.BackupError, "private_directory_permissions"):
            m.private_directory(self.work)

    def test_writer_and_reader_pair_must_be_distinct(self):
        for role, credential in CREDS.items():
            if role == "b2-reader": credential = CREDS["b2-writer"]
            p = self.path / (role + ".json")
            p.write_text(json.dumps({"accessKeyId": credential.access_id, "secretAccessKey": credential.secret}))
            p.chmod(0o600)
        with self.assertRaisesRegex(m.BackupError, "writer_reader_identity_not_separate"):
            m.load_credentials(self.path)

    def test_missing_credential_fails_before_network(self):
        with self.assertRaises(OSError): m.load_credentials(self.path)
        self.assertFalse(self.fake.calls)


    def test_systemd_acl_service_uid_read_only_accepted(self):
        entries = [(1, 4, 0xFFFFFFFF), (2, 4, 1234), (4, 0, 0xFFFFFFFF),
                   (16, 4, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)]
        raw = m.struct.pack("<I", 2) + b"".join(m.struct.pack("<HHI", *e) for e in entries)
        self.assertTrue(m.credential_acl_ok(raw, 1234))
        self.assertFalse(m.credential_acl_ok(raw, 1235))

    def test_systemd_acl_other_named_user_rejected(self):
        entries = [(1, 4, 0xFFFFFFFF), (2, 4, 1234), (2, 4, 5678),
                   (4, 0, 0xFFFFFFFF), (16, 4, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)]
        raw = m.struct.pack("<I", 2) + b"".join(m.struct.pack("<HHI", *e) for e in entries)
        self.assertFalse(m.credential_acl_ok(raw, 1234))

    def test_systemd_acl_group_read_rejected(self):
        entries = [(1, 4, 0xFFFFFFFF), (2, 4, 1234), (4, 4, 0xFFFFFFFF),
                   (16, 4, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)]
        raw = m.struct.pack("<I", 2) + b"".join(m.struct.pack("<HHI", *e) for e in entries)
        self.assertFalse(m.credential_acl_ok(raw, 1234))

    def test_systemd_acl_malformed_rejected(self):
        for raw in (b"", b"broken", m.struct.pack("<I", 999)):
            self.assertFalse(m.credential_acl_ok(raw, 1234))


if __name__ == "__main__":
    unittest.main(verbosity=2)
