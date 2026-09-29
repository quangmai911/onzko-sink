# SYS-LINK-001 — Backup and Recovery Runbook

**System:** ONZKO Branded Link Platform
**System ID:** SYS-LINK-001
**Environment Baseline:** STAGING
**Version:** v1.1
**Status:** CURRENT
**Date:** 29 September 2026

---

## 1. Purpose

This runbook defines how an authorised ONZKO operator recovers SYS-LINK-001 after code, data, cache, credential or configuration failure.

Do not assume code rollback restores data.

Determine the failure class before acting.

---

## 2. Current Staging Identity

Worker:

`onzko-link-stg`

URL:

`https://onzko-link-stg.mais.workers.dev`

Controlled Git branch:

`production`

Current known-good staging Worker version:

`55226e24-ad99-4baf-832b-5bf84eb796f8`

D1:

- name: `onzko-link-stg-d1`
- ID: `c5242151-701a-4880-8fad-9e810a279aa3`

KV:

- name: `onzko-link-stg-kv`
- ID: `373f18a7a06a42529105acdae27d20aa`

R2 logical backup:

- bucket: `onzko-link-stg-backups`;
- source schedule: `0 0,12 * * *`;
- status: COMMISSIONED.

Independent B2 recovery copy:

- bucket: `onzko-automation-prod-backups`;
- prefix: `systems/sys-link-001/staging/`;
- Object Lock default: Compliance / 30 days;
- status: COMMISSIONED.

Independent replication:

- host: `automation.onzko.com`;
- service: `onzko-link-backup.service`;
- timer: `onzko-link-backup.timer`;
- polling cadence: 15 minutes;
- status: ENABLED / COMMISSIONED.

---

## 3. Failure Classification

### Code failure

Examples:

- bad deployment;
- runtime regression;
- authentication regression;
- application error after release.

Primary action:

Cloudflare Worker rollback.

Do not restore D1 unless evidence indicates data corruption.

### Data failure

Examples:

- accidental link deletion;
- malformed bulk operation;
- database corruption;
- incorrect migration.

Primary action:

D1 Time Travel or logical restore.

Do not blindly roll back application code after schema-changing releases.

### KV/cache failure

Primary action:

Allow D1 fallback to regenerate cache.

Do not treat KV as authoritative link storage.

### Credential failure

Primary action:

Recover/rotate the affected credential from approved authorities.

Do not copy secrets into Git, chat, scripts or ordinary files.

### Configuration loss

Primary action:

Reconstruct from GitHub controlled configuration + registered Cloudflare resource identities.

---

## 4. Worker Rollback Procedure

Prerequisites:

- identify known-good version;
- verify compatibility with current D1 schema;
- use scoped Worker deployment credential.

Inspect deployments:

```bash
pnpm exec wrangler deployments list \
  --name onzko-link-stg \
  --config .wrangler/wrangler.link-stg-core.json
```

Inspect version:

```bash
pnpm exec wrangler versions view \
  <VERSION_ID> \
  --name onzko-link-stg \
  --config .wrangler/wrangler.link-stg-core.json
```

Rollback:

```bash
pnpm exec wrangler rollback \
  <KNOWN_GOOD_VERSION> \
  --name onzko-link-stg \
  --config .wrangler/wrangler.link-stg-core.json
```

After rollback verify:

- root HTTP 200;
- dashboard protected;
- API protected;
- public missing slug HTTP 404;
- machine API authentication HTTP 200;
- human application authentication HTTP 200;
- D1 expected state;
- KV expected state.

---

## 5. D1 Native Recovery Procedure

Use a temporary dedicated D1 recovery credential.

Do not broaden the routine Wrangler deployment token.

Before restore:

1. Capture current database counts/integrity.
2. Produce a full SQL safety export.
3. Retrieve Time Travel bookmark.
4. Establish the intended recovery point.
5. Confirm current application/schema compatibility.

Safety export pattern:

```bash
pnpm exec wrangler d1 export \
  onzko-link-stg-d1 \
  --remote \
  --output=<SAFE_PATH>.sql \
  --skip-confirmation
```

Time Travel information:

```bash
pnpm exec wrangler d1 time-travel info \
  onzko-link-stg-d1
```

Restore:

```bash
pnpm exec wrangler d1 time-travel restore \
  onzko-link-stg-d1 \
  --bookmark=<APPROVED_BOOKMARK>
```

After restore verify:

- required business data;
- table counts;
- migration marker/state;
- `PRAGMA foreign_key_check`;
- Worker health;
- API health;
- public redirect behaviour.

Capture the previous bookmark returned by Cloudflare until recovery has been validated.

Revoke the temporary D1 recovery credential immediately after successful recovery.

---

## 6. KV Recovery Procedure

D1 is authoritative.

For a missing KV cache entry:

1. Confirm authoritative link exists in D1.
2. Request the public slug.
3. Sink should fall back to D1.
4. Redirect should succeed.
5. Sink should repopulate the KV cache.

Do not restore KV from an old backup over newer D1 truth.

---

## 7. Secret Recovery Procedure

Permanent administrator/recovery authority:

Sticky Password.

Permanent staging records:

- ONZKO Link Staging — NUXT_SITE_TOKEN
- ONZKO Link Staging — NUXT_API_TOKEN
- ONZKO Link Staging — Cloudflare Access Service Token
- ONZKO Link Staging — Wrangler Deploy

Runtime authorities:

- Cloudflare Worker encrypted secrets;
- Cloudflare Zero Trust service credentials.

If a secret is suspected compromised:

1. rotate/reissue;
2. update runtime store;
3. verify service;
4. revoke old credential;
5. update SEC-001 metadata.

Never record the new secret value in documentation.

---

## 8. Configuration Reconstruction

Authoritative repository:

`quangmai911/onzko-sink`

Controlled branch:

`production`

Tracked configuration includes:

- `wrangler.jsonc`
- `.env.example`
- `scripts/cloudflare-deploy-config.mjs`
- `ops/sys-link-001/backup/README.md`
- `ops/sys-link-001/backup/src/onzko_link_backup.py`
- `ops/sys-link-001/backup/systemd/onzko-link-backup.service`
- `ops/sys-link-001/backup/systemd/onzko-link-backup.timer`
- `ops/sys-link-001/backup/config/config.staging.json`
- `ops/sys-link-001/backup/tests/test_replication.py`

Local `.env`, `.wrangler/` and `wrangler.deploy.jsonc` are not authoritative and may be recreated.

Current staging resource identifiers are recorded in BKR-001 / infrastructure control records.

---

## 9. Recovery Validation

A recovery is not complete because a command succeeded.

Verify:

- correct version/data restored;
- authentication still works;
- public redirects operate correctly;
- D1 integrity is clean;
- KV behaviour is consistent with D1;
- no temporary privileged credential remains;
- temporary recovery artefacts are removed;
- incident/change evidence is recorded.

---

---

## 10. Commissioned Backup Operating Model

D1 remains the authoritative source for link data.

KV is cache state and is not authoritative recovery data.

Logical scheduled exports are written to Cloudflare R2.

Source schedule:

`0 0,12 * * *`

Independent copies are replicated to Backblaze B2 by:

`onzko-link-backup.service`

with:

`onzko-link-backup.timer`

The replication timer polls every 15 minutes.

Controlled normal-age budget:

`45,780 seconds`

This remains below the internal independent-backup RPO target of <=24 hours.

The runtime value `rpo_guaranteed=false` is deliberately conservative and must not be treated as a forward-looking SLA.

B2 writer authority:

`writeFiles`

B2 verifier/reader authority:

`listFiles`, `readFiles`

The runtime identities do not have `deleteFiles`.

The writer does not have `readFiles`.

The verifier does not have `writeFiles`.

`listAllBucketNames` is not required.

---

## 11. Independent B2 Restore Procedure

Use the independent B2 copy when native recovery is unsuitable, unavailable, or when provider-independent recovery is required.

Identify the approved recovery point before restoring authoritative data.

Prefer a verified receipt under:

`/var/lib/onzko-link-backup/`

The receipt binds the source snapshot to the B2 data key, manifest key, SHA-256 and exact B2 VersionIds.

Retrieve `links.json` and `manifest.json` by their exact VersionIds using the approved B2 verifier/reader identity.

Use a private recovery directory with mode `0700`.

Recovered files should use mode `0600`.

Before application restore, verify:

- exact returned VersionIds;
- data SHA-256;
- manifest integrity;
- manifest/data binding;
- valid logical JSON structure;
- expected link count and identities.

Stop on any integrity mismatch.

Where practical, validate the recovered data through an isolated application environment before authoritative mutation.

Commissioning validated the recovered data through the real Sink `/api/link/import` and `/api/link/query` paths against isolated test D1.

Do not confuse Worker/code rollback with data recovery.

---
## 12. Replication Failure and Verification Checks

Operational attempt state:

`/var/lib/onzko-link-backup/last_attempt.json`

Last verified success:

`/var/lib/onzko-link-backup/last_success.json`

Verification receipts:

`/var/lib/onzko-link-backup/<receipt-id>.json`

Service:

`onzko-link-backup.service`

Timer:

`onzko-link-backup.timer`

Routine operator checks:

~~~bash
systemctl status onzko-link-backup.timer
systemctl list-timers onzko-link-backup.timer --all
systemctl status onzko-link-backup.service
journalctl -u onzko-link-backup.service
~~~

A timer being active does not by itself prove a verified backup.

Confirm:

- service result;
- exit status;
- `status=verified`;
- latest source age;
- expected snapshot count;
- exact B2 VersionId;
- last-success timestamp.

The implementation is designed to fail closed.

Commissioning validated:

- invalid private-directory permissions;
- network isolation;
- stale-source rejection;
- failed upload;
- corrupt read-back;
- incorrect VersionId;
- idempotent replay;
- preservation of the previous verified success after failure.

Do not weaken verification or broaden credentials merely to clear an operational fault.

---

## 13. Retention and Historical Evidence

Backblaze B2 Object Lock bucket default:

- mode: Compliance;
- duration: 30 days.

The commissioned runtime replication identities have no `deleteFiles` capability.

Historical recovery snapshots must not be manually removed by the runtime service.

Synthetic commissioning data may remain inside retained immutable snapshots after deletion from authoritative D1.

This is expected and preserves recovery evidence.

---

## 14. Commissioning Evidence

Commissioning demonstrated:

- real scheduled Cloudflare R2 export;
- representative non-empty logical backup;
- independent Backblaze B2 replication;
- SHA-256 verification;
- exact B2 VersionId capture;
- separate-identity read-back;
- manifest/data binding;
- private verification receipts;
- idempotent replay without duplicate versions;
- exact-version B2 recovery;
- isolated application-level restore;
- staging D1 non-mutation;
- controlled fail-closed behaviour;
- persistent systemd timer operation;
- unattended existing-snapshot verification;
- unattended new-source discovery and replication.

The first fully unattended new-source proof used the source exported at:

`2026-09-29T00:01:23.220Z`

The following replication polling cycle detected and copied it automatically.

Snapshot count advanced:

`9 → 10`

Verified SHA-256:

`4ac37fe7cbe715af8ddb5061209e932485c40a3e22db6dcf490097a06817416f`

Final commissioning B2 inventory:

- snapshot versions: 20;
- historical manual Object Lock test versions: 1;
- total versions: 21;
- delete markers: 0;
- latest exact data VersionId present: PASS.

The synthetic commissioning link:

`link-04g-recovery-proof`

was subsequently deleted through the normal authenticated application API.

Final authoritative staging state:

- synthetic-link query: HTTP 404;
- all-link count: 0;
- public synthetic route: HTTP 404.

Historical R2 and B2 recovery snapshots were retained.

---

## 15. Monitoring Boundary

LINK-04 backup and recovery controls are commissioned.

The wider production-readiness model still requires monitoring verification before SYS-LINK-001 can be declared production-ready.

Current native operational evidence includes:

- systemd timer state;
- systemd service result;
- journald execution records;
- `last_attempt.json`;
- `last_success.json`;
- source-age validation.

External or dead-man alerting for SYS-LINK-001 backup replication has not been declared commissioned by this runbook.

Do not declare:

`SYS-LINK-001 PRODUCTION OPERATING BASELINE APPROVED`

until applicable monitoring, functional QA, production commissioning and LINK-10 controls are separately satisfied.

---

## 16. LINK-04 Status

Verified:

- native recovery capability;
- logical export;
- retained logical export;
- independent off-platform recovery copy;
- exact-version independent restore;
- application-level restore validation;
- fail-closed behaviour;
- idempotency;
- unattended replication.

Gate:

> **LINK-04 RECOVERY PASS**

Environment:

**STAGING**

This status does not authorise production traffic or declare the production operating baseline approved.
