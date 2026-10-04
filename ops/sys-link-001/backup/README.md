# SYS-LINK-001 — Controlled Backup Replication Profiles

## Purpose

Replicate verified scheduled Sink logical backups from Cloudflare R2 to the
independent Backblaze B2 recovery estate.

## Controlled profiles

The replication implementation permits only two hard-coded environment
identities:

| Profile | Cloudflare R2 source | Backblaze B2 prefix |
|---|---|---|
| `staging` | `onzko-link-stg-backups` | `systems/sys-link-001/staging/` |
| `production` | `onzko-link-prod-backups` | `systems/sys-link-001/production/` |

The profile selector does not accept arbitrary R2 buckets, B2 prefixes,
storage endpoints or destination buckets.

`staging` remains the existing commissioned behaviour.

`production` is source-controlled but is not live-authorised merely because
the profile exists. Production installation, credentials, source scheduling,
first replication, recovery verification and unattended timer operation each
remain subject to later LINK-06F commissioning gates.

## Staging Runtime


Host:

`automation.onzko.com`

Service:

`onzko-link-backup.service`

Timer:

`onzko-link-backup.timer`

Source:

Cloudflare R2 bucket `onzko-link-stg-backups`

Destination:

Backblaze B2 bucket `onzko-automation-prod-backups`

Prefix:

`systems/sys-link-001/staging/`

## Credential boundaries

Runtime credentials are delivered through systemd `LoadCredential`.

Secrets are not stored in this repository.

Approved runtime identities:

- R2 reader
- B2 writer
- B2 recovery/verifier reader

B2 writer capability:

`writeFiles`

B2 reader capabilities:

`listFiles`, `readFiles`

Do not add:

- `listAllBucketNames`
- `deleteFiles`
- `readFiles` to the writer
- `writeFiles` to the reader

## Recovery controls

The replication implementation:

- validates scheduled R2 backups;
- enforces source-age limits;
- creates content-addressed B2 snapshot paths;
- captures exact B2 VersionIds;
- performs separate-identity exact-version read-back;
- verifies SHA-256;
- writes verified receipts;
- suppresses duplicate uploads through idempotent receipts;
- fails closed on invalid permissions or unavailable storage.

## Authority

GitHub repository:

`quangmai911/onzko-sink`

Controlled production branch:

`production`

This directory is the source authority for the SYS-LINK-001 off-platform
replication implementation.

Runtime credentials remain outside Git.
