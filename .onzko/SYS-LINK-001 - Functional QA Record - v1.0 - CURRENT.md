# SYS-LINK-001 — Functional QA Record

**System:** SYS-LINK-001 — ONZKO Branded Link Platform
**Environment:** STAGING
**Version:** v1.0
**Status:** CURRENT — QA PASS
**Date:** 4 October 2026
**Owner:** ONZKO
**Technical Authority:** ONZKO Technology Architecture
**Governing Control:** IOMCP-001
**Commissioning Gate:** LINK-05

---

## 1. Gate Decision

LINK-05 Functional QA is complete.

Final gate:

> **LINK-05 — QA PASS**

Environment:

**STAGING**

Status:

**CLOSED**

This record does not authorise production traffic, production DNS activation,
or `go.onzko.com` production commissioning.

---

## 2. Controlled Source and Runtime

Controlled repository:

`quangmai911/onzko-sink`

Controlled branch:

`production`

Controlled source revision:

`cf530c384365b1199def2881c418629948cfb51d`

Active known-good staging Worker version:

`9a0d9e22-005a-4742-9704-43f051bebfc1`

Traffic allocation:

`100%`

Staging Worker:

`onzko-link-stg`

Analytics Engine dataset:

`onzko_link_stg`

---

## 3. Pre-existing Gate Dependencies

LINK-03:

**SECURITY PASS / CLOSED**

LINK-04:

**RECOVERY PASS / CLOSED**

The LINK-05 review reused valid LINK-03 and LINK-04 evidence for
authentication, security, rollback and recovery rather than repeating
destructive recovery work unnecessarily.

---

## 4. Regression and Static Verification

Controlled-source verification included:

| Check | Result |
|---|---|
| Full Vitest suite | 28 files / 291 tests PASS |
| Targeted Analytics tests | 37 tests PASS |
| Runtime-source ESLint | PASS |
| TypeScript typecheck | PASS |
| Locale contracts | PASS |
| Git diff check for Analytics correction | PASS |

Full-repository lint also exposed pre-existing formatting/style debt in
non-runtime controlled documentation and Codex configuration files.

That formatting debt was not automatically rewritten during LINK-05 because
it was unrelated to runtime correctness and broad automatic formatting would
have expanded the controlled change scope.

---

## 5. Analytics Defect and Remediation

Initial staging reconciliation found no Analytics Engine binding on the
previous staging Worker.

An Analytics-enabled zero-traffic candidate was created with:

- `ANALYTICS` binding;
- staging dataset `onzko_link_stg`;
- `NUXT_CF_ACCOUNT_ID`;
- scoped `NUXT_CF_API_TOKEN`;
- existing D1, KV, R2, AI and Assets bindings preserved.

The first candidate proved that Analytics Engine writes succeeded but Sink's
Analytics read path returned empty results.

Direct Analytics Engine SQL verification proved the synthetic event existed.

Root cause:

Sink Analytics query code relied on Nuxt runtime configuration for:

- `NUXT_CF_ACCOUNT_ID`;
- `NUXT_CF_API_TOKEN`;
- `NUXT_DATASET`;

instead of reliably resolving the Cloudflare Worker runtime bindings.

Remediation was implemented through:

**PR #12 — Fix SYS-LINK-001 Analytics runtime bindings**

Merged production revision:

`cf530c384365b1199def2881c418629948cfb51d`

The correction:

- reads Worker-bound Analytics credentials first;
- reads the Worker-bound dataset first;
- retains Nuxt runtime configuration as fallback;
- applies the dataset resolver consistently across Analytics endpoints;
- adds regression coverage.

A second candidate was tested at zero normal traffic before promotion.

Result:

**PASS**

---

## 6. Functional QA Matrix

| Functional requirement | Evidence | Result |
|---|---|---|
| Normal redirect | public short link returned HTTP 301 to intended target | PASS |
| Custom slug | synthetic controlled slugs created and resolved | PASS |
| API create/query/edit/delete | expected 201/200/201/204 behaviour observed | PASS |
| Authentication | Cloudflare Access + Sink machine/human authentication proven | PASS |
| Destination change | target changed from example.com to example.org | PASS |
| Cache behaviour | immediate post-edit redirect returned new destination | PASS |
| Cache deletion | deleted link immediately returned HTTP 404 | PASS |
| Expiration | active before expiry; HTTP 404 immediately after expiry | PASS |
| Expired classification | expired record retained administratively and excluded from active list | PASS |
| Desktop route | default destination selected | PASS |
| Android route | Google destination selected | PASS |
| iPhone/iOS route | Apple destination selected | PASS |
| Chrome on iOS route | Apple destination selected | PASS |
| AU geography route | AU-specific destination selected | PASS |
| Geography fallback | non-matching AU request fell back to default destination | PASS |
| Analytics country | Cloudflare country recorded as AU | PASS |
| Analytics write | redirect produced Analytics Engine event | PASS |
| Analytics read | Sink API returned recorded event | PASS |
| Analytics counters | visits / visitors / referers returned successfully | PASS |
| Analysis UI | counters, trend, location, referer, device and OS data rendered | PASS |
| Realtime UI | live event stream, visit data and globe rendered | PASS |
| QR render | QR rendered successfully in dashboard | PASS |
| QR download | PNG download completed | PASS |
| QR scan | phone camera decoded staging short URL | PASS |
| QR end-to-end redirect | scanned QR redirected to intended target | PASS |
| Code rollback | previously demonstrated under controlled LINK-04 drill | PASS |
| Data recovery | LINK-04 RECOVERY PASS | PASS |

---

## 7. Known-Good Staging Runtime

Following zero-traffic verification, the Analytics runtime-fix candidate was
promoted to all staging traffic.

Known-good staging Worker:

`9a0d9e22-005a-4742-9704-43f051bebfc1`

Traffic:

`100%`

Post-promotion smoke verification included:

- public root reachable;
- dashboard protected by Cloudflare Access;
- API protected by Cloudflare Access;
- API documentation protected by Cloudflare Access;
- machine authentication successful;
- API create successful;
- public redirect successful;
- Analytics write/read successful;
- Analytics counters successful.

Result:

**PASS**

---

## 8. QA Data Cleanup

All synthetic `link05qa` short-link records were removed following QA.

Final cleanup proof:

- QA QR management query: HTTP 404;
- QA QR public route: HTTP 404;
- `link05qa` records remaining: `0`;
- temporary local credential variables/files cleaned.

Historical staging Analytics Engine events generated during QA are retained
as staging telemetry evidence. They are not active short-link records.

Result:

**PASS**

---

## 9. Authority Boundary

LINK-05 QA PASS authorises progression to a separate production
commissioning review.

It does not itself authorise:

- production DNS activation;
- production traffic;
- creation or activation of `go.onzko.com`;
- weakening Cloudflare Access;
- reuse of staging credentials as production credentials without review;
- production deployment without LINK-06 controls;
- uncontrolled creation of permanent public links.

---

## 10. Final Decision

The applicable functional QA requirements defined by IOMCP-001 have been
verified.

Therefore:

> **LINK-05 — QA PASS**

Environment:

**STAGING**

Status:

**CLOSED**

Next controlled stage:

**LINK-06 — Production Commissioning**

Production remains uncommissioned until LINK-06 independently passes.
