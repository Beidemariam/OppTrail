# The API

One surface, `/api/v2/*`, and three unversioned operations endpoints beside it.
104 endpoints; this is the shape they share rather than a list of all of them —
the generated OpenAPI schema at `/docs` (or `/openapi.json`) is the reference,
and `frontend/lib/api-types.ts` is generated from it.

## Authentication

A session cookie, set by `POST /api/v2/auth/signup` or
`POST /api/v2/auth/login`, `HttpOnly` and `Secure` when `ENVIRONMENT=production`.
`GET /api/v2/auth/me` answers who you are. Logging in rotates the session;
changing a password invalidates every session that user has.

**Every unsafe method needs a CSRF token**: the double-submit pair, a
non-`HttpOnly` `opptrail_csrf` cookie echoed in an `X-CSRF-Token` header. Any
safe request issues the cookie, so a client bootstraps it by loading a page or
calling `GET /api/health`. Login and signup are included — there is no
exemption.

```bash
jar=$(mktemp)
curl -sS -c "$jar" http://localhost:8000/api/health > /dev/null
csrf=$(awk '$6 == "opptrail_csrf" { print $7 }' "$jar")
curl -sS -b "$jar" -c "$jar" -X POST http://localhost:8000/api/v2/auth/login \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $csrf" \
  -d '{"email":"alex@opptrail.test","password":"opptrail-demo-123"}'
```

Login rotates the CSRF token with the session, so re-read the cookie after it.

## Every collection is a keyset page

```json
{ "items": [ … ], "next_cursor": "eyJ2IjpbIjIwMjYtMTAtMTdUMDk6MzA6MTJaIiwzXX0" }
```

`?limit=` is 1–200 and defaults to 50. `?cursor=` continues after the last row
of the previous page; it is an opaque base64 of that row's sort value and id, so
a row inserted at the head between requests cannot push a row you have already
seen onto the next page. The last page answers `next_cursor: null` rather than a
cursor that resolves to nothing — each query asks for one row more than the
limit to know that.

Walk a collection by following `next_cursor` until it is null. Do not construct
one.

## Every failure is one envelope

```json
{ "error": { "code": "validation_error",
              "message": "The request could not be validated",
              "fields": { "name": "This field is required" } } }
```

`fields` appears on a 422 and is keyed by the field path, so a form can put each
message where it belongs. The codes are stable: `validation_error`,
`bad_request`, `unauthorized`, `forbidden`, `not_found`, `conflict`,
`payload_too_large`, `unsupported_media_type`, `rate_limited`,
`internal_error`, `bad_gateway`, `service_unavailable`, `gateway_timeout`.

Two paths answer the envelope without reaching a handler: a CSRF rejection
(middleware answers before routing) and an unknown `/api/*` path, which 404s as
JSON rather than serving the single-page app.

## Permissions, and what absence looks like

Three roles — owner, editor, viewer — resolved from the database on every
request and never read from the client. **A deal you cannot see answers 404,
not 403**, so existence does not leak; 403 is reserved for "you can see this
and may not do that".

| Rule | Applies to |
|---|---|
| Any role | Reading a deal, its timeline, its members, asking the AI |
| Not a viewer | Writing an entry, a note, a comment, a reaction |
| Author or the deal's owner | Editing or deleting an existing item |
| Owner only | The record itself, sharing, the audit log, version history |

Two deliberate exceptions. `POST /api/v2/opportunities/{id}/watch` answers for
any signed-in caller, because following a deal you are not shared on is the
point of it — and watching grants no read access. And a **private entry** is
readable only by its author, including against the deal's owner: every read
that could return one filters it, and every write onto one answers 404.

## Timestamps

Every timestamp in and out is `YYYY-MM-DDTHH:MM:SSZ` — fixed-width UTC. They
are stored as text and compared lexicographically, so a different format does
not merely look wrong, it sorts wrong. A client-supplied `event_timestamp` is
normalized at the boundary or rejected.

`event_timestamp` is when the thing happened and may be edited; `created_at` is
when the row was written and may not.

## Writes worth knowing about

- **`PATCH` is partial.** Send only the keys that changed. An empty patch
  writes nothing and publishes nothing.
- **A note edit carries a guard.** `PATCH /api/v2/notes/{id}` requires
  `updated_at` — the value the editor was opened against — and answers **409**
  if the note has moved since. It is required rather than optional, because the
  client that omits it is exactly the one that would clobber.
- **`custom_values` is written whole.** Omitting the key leaves the stored set
  alone; `{}` clears it. A value is validated against the live field
  definitions and a 422 names the field.
- **Deletes are soft, and undoable.** `DELETE` stamps `deleted_at` and cascades
  down opportunity → entry → note → comment → reply;
  `POST .../{id}/restore` takes back exactly what that delete took. Restoring
  something that is not deleted is a 404, like restoring something that never
  existed.
- **An edit is recoverable.** Opportunities, entries, notes and tasks each keep
  a snapshot per write, read with `GET .../versions` (owner only) and put back
  with `POST .../versions/{n}/restore`.

## Two streams, and they are not the same shape

`GET /api/v2/opportunities/{id}/events` is `text/event-stream` carrying
**invalidations only** — `{"type":"timeline.changed","opportunity_id":7}` — so
nothing about what a row contains or who may read it is decided twice. The
client refetches. A stream closes itself after five minutes having advertised a
`retry:`, and the browser reopens it; treat a reconnect as a gap and refetch.

`POST /api/v2/opportunities/{id}/ai/ask/stream` is the other one: a POST,
because the question is in the body, and it carries **content** — `delta`
events as the answer is written, then `done` with the citations. A failure
mid-stream is an `error` event, not a status code, because the status line is
long gone.

## Rates and sizes

Login and signup are rate limited per source address. An upload is capped by
size and by **sniffed** content type — the declared filename and MIME type are
metadata, and a `.exe` renamed `.pdf` is a 415.

## The operations endpoints

| Endpoint | Question | Answer |
|---|---|---|
| `GET /healthz` | Is the process answering? | 200, no I/O |
| `GET /readyz` | Can it serve a write? | 200, or 503 |
| `GET /api/health` | What state is the deployment in? | schema version, writability, last backup, newest run of each job |

Unversioned on purpose: a probe that moves when the client API changes shape
can break a deployment for a reason unrelated to deployment.
