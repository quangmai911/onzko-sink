# SYS-LINK-001 — Backup and Recovery Runbook

**System:** ONZKO Branded Link Platform
**System ID:** SYS-LINK-001
**Environment Baseline:** STAGING
**Version:** v1.0
**Status:** CURRENT
**Date:** 20 September 2026

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

R2 backup:

NOT YET COMMISSIONED.

Automatic application backup:

DISABLED.

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

## 10. Current Limitations

Persistent Cloudflare logical backup is not yet commissioned.

Independent Backblaze B2 recovery copy is not yet commissioned.

Until both are implemented and restore-tested:

> **SYS-LINK-001 does not satisfy the complete LINK-04 RECOVERY PASS gate.**

See:

`BKR-001 - SYS-LINK-001 Backup and Recovery Matrix - v1.0 - CURRENT.md`

---

## 11. Next Recovery Control

`LINK-04G — Persistent Logical Backup + Independent Off-Platform Copy`
