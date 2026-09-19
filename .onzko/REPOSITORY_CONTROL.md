# SYS-LINK-001 — Repository Control Baseline

## Control Identity

- System: SYS-LINK-001 — ONZKO Branded Link Platform
- Repository: quangmai911/onzko-sink
- Upstream: miantiao-me/Sink
- Licence: AGPL-3.0-only
- Repository authority: GitHub
- Control framework: IOMCP-001
- Commissioning stage: LINK-01 — Sink Repository Baseline

## Branch Authority

### master

Purpose:

Upstream-tracking branch.

Rules:

- Tracks miantiao-me/Sink master.
- Must remain as close to upstream as practical.
- Must not contain ONZKO production secrets.
- Must not be treated as automatically approved production code.
- Upstream synchronisation does not constitute production approval.

### production

Purpose:

ONZKO-controlled production-eligible code baseline.

Rules:

- Protected branch.
- No force pushes.
- No branch deletion.
- Changes must pass through pull request control.
- Production deployment requires the relevant ONZKO release/change gate.
- Cloudflare must not automatically deploy unreviewed upstream changes.

## Initial Baseline

Upstream repository:

miantiao-me/Sink

Initial controlled commit:

6751f16d982a010eb390e101f9a9a974ea2d1ce4

Initial state:

master and production were identical when the production branch was established.

## Upstream Update Policy

Use:

```text
UPSTREAM CHANGE
    ↓
RELEVANCE / SECURITY REVIEW
    ↓
SYNC master
    ↓
CREATE upgrade branch
    ↓
TEST
    ↓
PULL REQUEST
    ↓
production
    ↓
STAGING
    ↓
PRODUCTION APPROVAL
    ↓
DEPLOY
    ↓
VERIFY
```

Upstream changes must not automatically become ONZKO production changes.

## Release Policy

Upstream version and ONZKO production release are separate concepts.

Example:

Upstream:
v0.3.0

ONZKO production release:
sys-link-001-v0.1.0

Production tags are created only after the corresponding release has passed the required ONZKO staging, approval and verification gates.

## Secrets Policy

Never commit:

- Cloudflare API tokens
- site tokens
- passwords
- private keys
- service credentials
- database credentials
- backup credentials
- n8n credentials
- password-manager exports

Secrets belong in approved runtime secret stores or the approved ONZKO credential-management system.

## Deployment Authority

This repository owns source code and controlled deployment configuration.

It does not itself authorise production deployment.

Production deployment remains subject to the ONZKO Infrastructure & Orchestration Master Control gates.

## Current Deployment State

At LINK-01:

- Cloudflare Worker: NOT CREATED
- D1: NOT CREATED
- KV: NOT CREATED
- R2: NOT CREATED
- production DNS: UNCHANGED
- go.onzko.com: NOT COMMISSIONED

## Next Gate

LINK-02 — CLOUDFLARE STAGING

LINK-02 may begin only after LINK-01 is formally closed as:

REPOSITORY CONTROLLED
