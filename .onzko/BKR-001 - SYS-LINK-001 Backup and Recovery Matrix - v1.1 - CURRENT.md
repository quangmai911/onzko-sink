# BKR-001 — SYS-LINK-001 Backup and Recovery Matrix

**System:** SYS-LINK-001 — ONZKO Branded Link Platform
**Environment:** STAGING
**Version:** v1.1
**Status:** CURRENT — RECOVERY PASS
**Date:** 29 September 2026
**Owner:** ONZKO
**Technical Authority:** ONZKO Technology Architecture
**Governing Control:** IOMCP-001

---

## 1. Recovery Objectives

SYS-LINK-001 uses layered recovery.

Internal targets:

- Independent-backup RPO: <=24 hours.
- Significant-service RTO: <=2 hours.
- Critical permanent production slugs receive highest restoration priority.

The independent-backup RPO target is met by the commissioned 12-hour logical source schedule plus 15-minute independent replication polling. The controlled normal-age budget is 45,780 seconds (approximately 12 hours 43 minutes), below the <=24-hour target. The runtime field `rpo_guaranteed=false` remains deliberately conservative and is not itself a forward-looking availability guarantee.

---

## 2. Backup and Recovery Matrix

| ID | Protected Resource | Mechanism | Frequency | Retention | Independent Copy | RPO / RTO | Restore Verification | Status / Gap |
|---|---|---|---|---|---|---|---|---|
| BKR-0001 | D1 authoritative link database `onzko-link-stg-d1` | Cloudflare D1 Time Travel + SQL export | Native continuous history; SQL export currently ad hoc | Native retention provider/plan dependent; temporary test export deleted | Independent copy provided by BKR-0006; this native layer itself is not provider-independent | Significant-service RTO <=2h demonstrated; independent-backup RPO is provided by BKR-0006 | Actual Time Travel restore PASS 2026-09-20 | PASS for native recovery |
| BKR-0002 | Worker application/code | GitHub `production` + Cloudflare Worker versions/deployments | Every controlled change/deployment | Git/version history | GitHub provides provider-separated code authority | RTO <=2h demonstrated | Actual deployment + rollback PASS 2026-09-20 | PASS |
| BKR-0003 | Workers KV cache | Rebuild automatically from authoritative D1 | On cache miss | Cache lifecycle only | Not required as authoritative backup | No authoritative-data RPO requirement; RTO <=2h demonstrated | Manual KV-loss/rebuild drill PASS 2026-09-20 | PASS |
| BKR-0004 | Secrets and deployment configuration | Sticky Password + Cloudflare runtime stores + GitHub configuration authority | At change | Current controlled records | Human recovery copy separated from runtime | RTO <=2h demonstrated operationally | Exact config reconstruction and credential recovery PASS 2026-09-20 | PASS |
| BKR-0005 | Retained logical link export | Cloudflare R2 bucket `onzko-link-stg-backups` scheduled Sink logical export | 12-hour source schedule: `0 0,12 * * *` | Retained source snapshots; independent recovery does not depend on R2 retention alone | No — Cloudflare layer | Normal-age budget 45,780s; below <=24h target | Real non-empty export verified; exact source restored and application-import tested | PASS |
| BKR-0006 | Independent off-platform recovery copy | Backblaze B2 bucket `onzko-automation-prod-backups`, prefix `systems/sys-link-001/staging/` | 15-minute systemd poll; new scheduled sources copied automatically | B2 Object Lock default: Compliance, 30 days | YES — independent provider | Independent-backup RPO <=24h target satisfied by controlled schedule | Exact B2 VersionId read-back, SHA-256 verification, isolated application restore and unattended new-source replication PASS | PASS |

---

## 3. Recovery Evidence — D1

**Database:** `onzko-link-stg-d1`
**Database ID:** `c5242151-701a-4880-8fad-9e810a279aa3`

Baseline before restore drill:

- links: 0
- link_tombstones: 0
- tags: 0
- link_tags: 0
- link_migration_runs: 1
- d1_migrations: 5
- migration status: completed
- foreign-key check: clean

Drill procedure:

1. Full SQL safety export created.
2. Synthetic recovery table created.
3. Row A inserted.
4. Time Travel bookmark captured.
5. Row B inserted after bookmark.
6. Time Travel restore executed to captured bookmark.
7. Row A survived.
8. Row B disappeared.
9. Application-table counts remained unchanged.
10. Migration state remained unchanged.
11. Foreign-key check remained clean.
12. Synthetic table removed.
13. Temporary D1 Write credential revoked and verification returned HTTP 401.

**Result:** PASS.

---

## 4. Recovery Evidence — KV

Synthetic link:

`link-04c-kv-recovery`

Evidence:

- API create: HTTP 201.
- Redirect before cache loss: HTTP 301.
- `link:link-04c-kv-recovery` confirmed in KV.
- KV key manually removed.
- Public redirect after KV loss: HTTP 301.
- KV key automatically recreated from D1 fallback.
- Test link deleted through normal API: HTTP 204.
- Public route after cleanup: HTTP 404.
- KV namespace returned to zero entries.

**Conclusion:** D1 is authoritative. KV is recoverable cache state and does not require an independent authoritative link backup.

**Result:** PASS.

---

## 5. Recovery Evidence — Worker Rollback

Known-good version:

`55226e24-ad99-4baf-832b-5bf84eb796f8`

Controlled test version:

`4012866f-2f58-4169-9f44-dbf5ebcf7c92`

Procedure:

1. Test version deployed to 100% staging traffic.
2. Service and authentication validated.
3. Worker rolled back to known-good version.
4. Known-good version returned to 100% traffic.
5. Edge checks after rollback:
   - root: HTTP 200
   - dashboard: HTTP 302
   - unauthenticated API: HTTP 302
   - missing public slug: HTTP 404
6. Machine authentication: HTTP 200 / `api-token`.
7. Human application token: HTTP 200 / `site-token`.
8. D1 link count remained 0.
9. KV remained empty.

**Result:** PASS.

---

## 6. Recovery Evidence — Secrets and Configuration

Authoritative sources:

- GitHub `production` — code and controlled configuration.
- Sticky Password — human/recovery secret values.
- Cloudflare Worker encrypted secrets — runtime secret authority.
- Cloudflare Zero Trust — Access/service identity authority.

Permanent Sticky Password records confirmed:

- ONZKO Link Staging — NUXT_SITE_TOKEN
- ONZKO Link Staging — NUXT_API_TOKEN
- ONZKO Link Staging — Cloudflare Access Service Token
- ONZKO Link Staging — Wrangler Deploy

Temporary D1 Recovery Drill credential:

- revoked;
- verification returned HTTP 401;
- Sticky Password temporary record removed.

Recovery reconstruction:

- staging core Wrangler configuration reconstructed exactly from controlled source + registered resource identifiers;
- build-only environment reconstructed exactly;
- runtime secret names verified from deployed Worker version;
- secret values were not placed in Git or recovery documentation.

**Result:** PASS.

---

## 7. Recovery Authority

### Data authority

D1 is the authoritative source for link data.

KV is cache/legacy migration state and may be rebuilt from D1.

### Code authority

GitHub `production` is the controlled code authority.

Cloudflare Worker versions provide operational rollback capability.

### Secret authority

Sticky Password is the approved administrator/recovery vault.

Cloudflare encrypted Worker secrets and Zero Trust service credentials are runtime authorities.

Secret values must never be recorded in BKR-001, SEC-001, Git, ordinary Drive files, or recovery documentation.

---

## 8. Commissioned Logical + Independent Recovery Layer

### Cloudflare R2 source

Commissioned bucket:

`onzko-link-stg-backups`

Scheduled logical source:

`0 0,12 * * *`

The application creates recoverable logical JSON exports under the governed scheduled-backup prefix.

A non-empty commissioning record was used to prove that the export preserved representative authoritative link fields.

### Independent Backblaze B2 recovery estate

Bucket:

`onzko-automation-prod-backups`

Exact governed prefix:

`systems/sys-link-001/staging/`

Runtime B2 writer capabilities:

`writeFiles`

Runtime B2 verifier/reader capabilities:

`listFiles`, `readFiles`

Explicitly excluded:

- `deleteFiles`;
- writer `readFiles`;
- reader `writeFiles`;
- `listAllBucketNames`.

The runtime implementation performs no remote delete operation.

B2 Object Lock bucket default was verified as:

- mode: Compliance;
- duration: 30 days.

### Git and runtime authority

Controlled repository:

`quangmai911/onzko-sink`

Controlled branch:

`production`

Backup implementation authority:

`ops/sys-link-001/backup/`

Commissioned Git baseline entered `production` through PR #9.

Production merge commit:

`b2786009280e604de5dbfc562f8fcc09cab8500e`

Runtime:

- host: `automation.onzko.com`;
- service: `onzko-link-backup.service`;
- timer: `onzko-link-backup.timer`;
- state: `/var/lib/onzko-link-backup`;
- state-directory mode: `0700`;
- runtime-directory mode: `0700`.

The timer is enabled and operates on an independent 15-minute poll schedule.

### Integrity and idempotency evidence

The independent-copy implementation verifies:

- scheduled-source object identity;
- source size and freshness;
- conditional source read;
- SHA-256;
- exact B2 object VersionId;
- separate writer and verifier identities;
- read-back of the exact uploaded version;
- manifest binding;
- content-addressed destination path;
- private atomic verification receipts;
- idempotent replay without duplicate versions.

Offline regression suite:

- 56 tests;
- PASS.

Controlled failure testing demonstrated:

- invalid private-directory permissions fail closed;
- network isolation fails closed;
- previous successful state is not overwritten by a false success.

### Restore evidence

Independent restore testing retrieved the commissioned B2 copy by exact VersionId.

Verified:

- exact data VersionId;
- exact manifest VersionId;
- data SHA-256;
- manifest SHA-256;
- manifest/data binding;
- logical JSON structure;
- representative fields.

The recovered logical data was then exercised through the real Sink `/api/link/import` and `/api/link/query` application paths against an isolated test D1 environment.

Result:

- application restore PASS;
- staging authoritative D1 non-mutation PASS.

### Unattended operating evidence

First timer-owned execution:

- timer triggered automatically;
- service exited successfully;
- exact existing B2 versions were reverified;
- no duplicate object versions were created.

First new-source unattended replication:

- scheduled source exported at `2026-09-29T00:01:23.220Z`;
- next replication poll detected the new source automatically;
- snapshot count advanced from 9 to 10;
- SHA-256: `4ac37fe7cbe715af8ddb5061209e932485c40a3e22db6dcf490097a06817416f`;
- new exact B2 VersionId captured and verified.

Final B2 inventory after the new snapshot:

- snapshot versions: 20;
- historical manual Object Lock test versions: 1;
- total versions: 21;
- delete markers: 0;
- latest exact data VersionId present: PASS.

### Commissioning-data cleanup

Synthetic staging record:

`link-04g-recovery-proof`

was deleted through the normal authenticated Sink API after all recovery evidence was complete.

Final authoritative staging state:

- query synthetic slug: HTTP 404;
- all-link count: 0;
- public synthetic route: HTTP 404.

Historical R2/B2 snapshots containing the synthetic record remain retained recovery evidence and were not deleted.

---

## 9. Gate Status

Verified:

- native D1 recovery: PASS;
- logical export: PASS;
- retained logical export: PASS;
- D1 Time Travel restore: PASS;
- KV rebuild: PASS;
- Worker rollback: PASS;
- secrets/config reconstruction: PASS;
- independent B2 recovery copy: PASS;
- exact-version independent restore: PASS;
- application-level restore validation: PASS;
- idempotency: PASS;
- fail-closed behaviour: PASS;
- unattended timer execution: PASS;
- unattended new-source replication: PASS;
- commissioning-data cleanup: PASS.

Therefore:

> **LINK-04 RECOVERY PASS**

This gate establishes the backup and recovery control for the STAGING environment.

It does **not** declare SYS-LINK-001 production commissioned or approve the full production operating baseline.

Remaining lifecycle controls include LINK-05 functional QA, subsequent production commissioning controls, and monitoring verification required by the broader production-readiness / LINK-10 operating-baseline model.
