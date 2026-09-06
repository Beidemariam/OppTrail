# 0008. Attachments on the local filesystem, streamed through the API

Status: Accepted (v2)

## Context

Attachments are new in v2 (an explicit MVP non-goal until now) and are required by
both the attachment feature and inbound email (ADR 0009). Access must respect
opportunity sharing.

## Options

1. **Object storage** (S3 or compatible) with presigned URLs.
2. **Local filesystem** under the existing `/data` volume, served through FastAPI.
3. **Blobs in SQLite.**

## Decision

**Option 2.** The container already mounts a persistent `/data` volume for the
database; attachments sit beside it and are covered by the same backup (ADR 0011).
S3 adds a credential, a bill and a dependency for a workload measured in megabytes.
Option 3 bloats the database file and breaks the "copy one file" backup story at
size.

- Content-addressed layout: `/data/attachments/{sha256[:2]}/{sha256}`, so identical
  uploads deduplicate and filenames never touch the filesystem.
- Metadata row: `attachments(id, sha256, filename, content_type, byte_size,
  uploaded_by, entity_type, entity_id, created_at, deleted_at)`.
- **Never served as static files.** Download goes through
  `GET /api/attachments/{id}` which runs the same `require_opportunity_access`
  check as everything else and then streams the file. Serving `/data` statically
  would reintroduce exactly the containment bug fixed in `main.py:56-64`.
- Validation: size cap (10 MB default), extension allowlist, and **magic-byte
  sniffing** — never trust the client `Content-Type`.
- Responses set `Content-Disposition: attachment` and
  `X-Content-Type-Options: nosniff`; SVG is either excluded or forced to download,
  since it executes script when rendered inline.
- No virus scanning in v2. At 20 known internal users the residual risk is low;
  ClamAV is the drop-in if that changes. Recorded as an accepted risk.
- Thumbnails deferred to v3 — an image preview needs no server-side resize at this
  volume.

## Consequences

- Attachments are bound to the single container's disk. Same trigger as ADR 0001;
  they move together.
- Streaming through the app costs a worker slot per download. Fine at this scale.
