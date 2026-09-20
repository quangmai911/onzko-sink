# BKR-001 — SYS-LINK-001 Backup and Recovery Matrix

**System:** SYS-LINK-001 — ONZKO Branded Link Platform
**Environment:** STAGING
**Version:** v1.0
**Status:** CURRENT — RECOVERY BASELINE / GATE HOLD
**Date:** 20 September 2026
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

The independent-backup RPO target is NOT YET MET because persistent logical backup and off-platform replication have not yet been commissioned.

---

## 2. Backup and Recovery Matrix

| ID | Protected Resource | Mechanism | Frequency | Retention | Independent Copy | RPO / RTO | Restore Verification | Status / Gap |
|---|---|---|---|---|---|---|---|---|
| BKR-0001 | D1 authoritative link database `onzko-link-stg-d1` | Cloudflare D1 Time Travel + SQL export | Native continuous history; SQL export currently ad hoc | Native retention provider/plan dependent; temporary test export deleted | No persistent independent copy yet | Significant-service RTO <=2h demonstrated; independent RPO not satisfied by this layer | Actual Time Travel restore PASS 2026-09-20 | PASS for native recovery |
| BKR-0002 | Worker application/code | GitHub `production` + Cloudflare Worker versions/deployments | Every controlled change/deployment | Git/version history | GitHub provides provider-separated code authority | RTO <=2h demonstrated | Actual deployment + rollback PASS 2026-09-20 | PASS |
| BKR-0003 | Workers KV cache | Rebuild automatically from authoritative D1 | On cache miss | Cache lifecycle only | Not required as authoritative backup | No authoritative-data RPO requirement; RTO <=2h demonstrated | Manual KV-loss/rebuild drill PASS 2026-09-20 | PASS |
| BKR-0004 | Secrets and deployment configuration | Sticky Password + Cloudflare runtime stores + GitHub configuration authority | At change | Current controlled records | Human recovery copy separated from runtime | RTO <=2h demonstrated operationally | Exact config reconstruction and credential recovery PASS 2026-09-20 | PASS |
| BKR-0005 | Retained logical link/database export | Intended Cloudflare R2 logical backup | TARGET: at least daily | TBD during commissioning | No — same provider layer | Independent RPO <=24h not yet met | Not implemented / not restored | BLOCKING |
| BKR-0006 | Independent off-platform recovery copy | Intended Backblaze B2 copy of recoverable logical export | TARGET: at least daily | TBD during commissioning | YES once commissioned | Independent RPO <=24h target | Not implemented / restore not tested | BLOCKING |

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

## 8. Open Recovery Gaps

### HOLD-LINK-04-001 — Persistent logical backup not commissioned

Current staging configuration:

- R2 binding: absent.
- `NUXT_DISABLE_AUTO_BACKUP=true`.
- Sink contains logical R2 backup capability but it is not active.

Required remediation:

- commission controlled Cloudflare R2 backup storage;
- create retained logical backups;
- define retention;
- verify backup contents;
- test restore/readability.

### HOLD-LINK-04-002 — Independent off-platform copy not commissioned

Required remediation:

- copy recoverable logical backup to approved Backblaze B2 recovery estate;
- frequency sufficient for <=24 hour independent-backup RPO;
- define retention;
- verify integrity;
- conduct restore test independent of Cloudflare.

---

## 9. Gate Status

Completed:

- native D1 recovery: PASS;
- logical export capability: PASS;
- D1 restore: PASS;
- KV rebuild: PASS;
- Worker rollback: PASS;
- secrets/config reconstruction: PASS.

Not completed:

- retained logical export: OPEN;
- independent off-platform recovery copy: OPEN.

Therefore:

> **LINK-04 RECOVERY PASS — NOT YET AUTHORISED**

Next recovery remediation:

> **LINK-04G — PERSISTENT LOGICAL BACKUP + INDEPENDENT OFF-PLATFORM COPY**
