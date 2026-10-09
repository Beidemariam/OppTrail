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

## Amendments (milestone 4.3, 2026-10-01)

Implemented as decided, with three changes to the detail above and one risk
restated. Each is argued in `docs/autopilot/DECISIONS.md`.

- **The metadata row has `entry_id`, not `entity_type`/`entity_id`**
  (**D-148**). `docs/ROADMAP.md` is explicit that an attachment hangs off the
  entry it belongs to, and one parent spelled as a foreign key keeps the key,
  the index and the soft-delete cascade that a polymorphic pair gives up. A
  second kind of parent is an additive migration if v3's email ingestion needs
  one.
- **The content-addressed layout replaced Phase F's random stored name**
  (**D-147**). `app/uploads.py` was written in F.5 with
  `secrets.token_hex(16)` and a flat root; this ADR's `{sha256[:2]}/{sha256}`
  is what ships, because the digest also deduplicates. The containment check
  kept both of its independent halves and gained a level for the shard
  directory.
- **The type allowlist includes the three OOXML formats** (**D-150**) — Word,
  Excel and PowerPoint — because the documents this feature exists for arrive
  in them. They share one magic signature, so they are separated by the part
  prefix in the archive's central directory, and a macro-carrying archive is
  refused. Legacy OLE2 `.doc`/`.xls` are not accepted.
- **Deleting an attachment never removes the file** (**D-149**). The row is
  soft-deleted and restorable, and a content-addressed blob may be shared with
  a row nobody deleted, so the only safe prune predicate also has to consider
  what a restore of an ADR 0011 backup would name. Uploads join the backup
  story in Phase R (R.5), which is where a pruner belongs.
- **The size cap refuses what is stored, not what is received** (**D-153**).
  The multipart parser spools the request before the handler runs. Recorded as
  an accepted risk alongside the absence of virus scanning, with a
  request-size middleware named as the fix if it stops being acceptable.

One thing above is unchanged and worth repeating because it is the whole
access-control argument: **the files are never served statically.** Download
is `GET /api/v2/attachments/{id}/download` (the path is `/api/v2` rather than
this ADR's `/api/attachments/{id}`, since v2 is the one API surface), it runs
`require_opportunity_access`, and `tests/test_attachments.py` asserts that no
static path reaches the volume.
