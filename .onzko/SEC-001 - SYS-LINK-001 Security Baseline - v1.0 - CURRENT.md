# SEC-001 — SYS-LINK-001 Security Baseline

**System:** SYS-LINK-001 — ONZKO Branded Link Platform
**Environment:** STAGING
**Version:** v1.0
**Status:** CURRENT — SECURITY PASS
**Date:** 4 October 2026
**Owner:** ONZKO
**Technical Authority:** ONZKO Technology Architecture
**Governing Control:** IOMCP-001

---

## 1. Security Architecture

SYS-LINK-001 staging uses layered authentication.

Public short-link routes remain publicly reachable.

Administrative and API surfaces are protected first by Cloudflare Access at the edge and then by Sink application authentication.

Current model:

    PUBLIC SHORT LINKS
            |
            +--> public

    ADMIN / API / DOCS
            |
            +--> Cloudflare Access
                    |
                    +--> Sink application authentication
                            |
                            +--> human: NUXT_SITE_TOKEN
                            |
                            +--> machine: NUXT_API_TOKEN

Sink's optional internal Cloudflare Access JWT integration is not enabled.

`accessEnabled=false` from `/api/verify` therefore describes Sink runtime configuration only. It does not mean Cloudflare Access edge protection is disabled.

This configuration is intentional for the current staging baseline.

---

## 2. Controlled Source and Runtime Identity

Controlled repository:

`quangmai911/onzko-sink`

Controlled branch:

`production`

Controlled source baseline at security closure:

`4e8c57322ee57bee3e17e3694e08826a13ea310e`

Staging Worker:

`onzko-link-stg`

Current staging Worker version:

`b6e6a5cd-b077-4c72-9b5e-145cf987f0f4`

Traffic allocation:

`100%`

---

## 3. Runtime Authentication Secrets

Verified staging secret names:

- `NUXT_API_TOKEN`
- `NUXT_SITE_TOKEN`

Secret values are not recorded in Git or this document.

Human/recovery values remain in approved secure credential custody.

---

## 4. Edge Protection Evidence

Unauthenticated staging requests produced:

| Surface | Result |
|---|---|
| `/` | HTTP 200 |
| `/dashboard` | HTTP 302 to Cloudflare Access |
| `/dashboard/login` | HTTP 302 to Cloudflare Access |
| `/api/verify` | HTTP 302 to Cloudflare Access |
| `/_docs` | HTTP 302 to Cloudflare Access |

Conclusion:

- public service surface remains reachable;
- dashboard is protected;
- dashboard login is protected;
- API is protected;
- API documentation is protected.

---

## 5. Human Authentication Evidence

Verified human flow:

    Cloudflare Access authentication
            ↓
    Sink login
            ↓
    NUXT_SITE_TOKEN
            ↓
    Dashboard
            ↓
    Links page

The staging dashboard and Links view loaded successfully after authentication.

Result:

**PASS**

---

## 6. Machine Authentication Evidence

The controlled machine path uses:

    Cloudflare Access service identity
            +
    NUXT_API_TOKEN

Previous controlled verification returned:

- HTTP 200;
- `authMethod=api-token`;
- `userID=machine`;
- `accessEnabled=false`.

The `accessEnabled=false` field is expected because Sink's optional application-level Cloudflare Access JWT validation is not enabled.

The Cloudflare Access edge remains a separate security layer.

Result:

**PASS**

---

## 7. Authority Boundaries

The current staging security baseline does not authorise:

- production traffic;
- production DNS activation;
- `go.onzko.com`;
- autonomous administrative writes;
- weakening Cloudflare Access;
- removal of Sink authentication;
- storage of credential values in Git or ordinary documentation.

Any change to the authentication architecture requires controlled review.

---

## 8. Gate Status

Verified:

- Cloudflare Access edge protection: PASS;
- dashboard protection: PASS;
- API protection: PASS;
- documentation/admin protection: PASS;
- human authentication: PASS;
- machine authentication: PASS;
- separate human/machine Sink credentials: PASS;
- scoped secret handling: PASS;
- public short-link surface separation: PASS.

Therefore:

> **LINK-03 SECURITY PASS**

Environment:

**STAGING**

This gate does not authorise production traffic or declare SYS-LINK-001 production commissioned.
