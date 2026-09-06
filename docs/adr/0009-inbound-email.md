# 0009. Inbound email via IMAP polling, addressed by signed token

Status: Accepted (v2)

## Context

Creating entries, notes and comments **by email** is a confirmed v2 requirement.
This is the highest-risk feature in the plan: it accepts content from outside the
application's authentication boundary and puts it into a shared sales record and
into the AI's context (see ADR 0012 on prompt injection).

`AGENTS.md` currently lists email integration as a non-goal; that list needs
updating (Phase 2 deliverable).

## Options

1. **Provider inbound webhook** (Postmark, SendGrid, Mailgun) POSTing parsed mail to
   `/api/inbound/email`. Clean parsing, needs a public HTTPS endpoint, DNS/MX
   configuration and an account.
2. **IMAP polling** of one mailbox from the background scheduler (ADR 0004). No
   public endpoint, no inbound DNS, works on a laptop or a private network.
3. Running an SMTP server. Rejected — operating mail transport is out of scope.

## Decision

**Option 2 for v2**, with the parser written behind an interface so option 1 becomes
a transport swap rather than a rewrite. IMAP suits the stated deployment (single
self-hosted container, minimal ops appetite): no inbound firewall hole, no MX
records, no third-party account.

### Addressing

A reply address encodes the target and a signature:
`opptrail+{kind}-{id}-{hmac}@mailbox.example`, where `hmac = HMAC-SHA256(secret,
"{kind}:{id}")` truncated. `kind` is `opp` (creates an entry), `entry` (creates a
note) or `note` (creates a comment).

This finally gives `settings.session_secret` — currently dead configuration — a real
purpose, or better, a dedicated `INBOUND_EMAIL_SECRET`.

Every notification email sets `Reply-To` to the matching address, so replying to a
comment notification posts a comment. That is the interaction that makes the feature
feel native rather than bolted on.

### Trust model

The signed address proves *which object*, never *who*. Email `From:` is trivially
spoofable, so:

1. The address HMAC must verify, or the message is dropped silently.
2. `From:` is matched to a known user; unknown senders are rejected with a bounce.
3. That user must pass the normal write check for the target opportunity — the same
   `require_timeline_write` path as the HTTP API. **No new authorization path.**
4. DKIM must pass where present; failures are quarantined rather than posted.
5. Deduplicate on `Message-ID`, persisted, so a re-poll cannot double-post.
6. Rate-limit per sender.

### Content

Quoted-reply and signature stripping, HTML to Markdown, attachments through
ADR 0008 with the same caps. Every email-originated record is flagged
`source = 'email'` and rendered with a visible marker — provenance must not be
ambiguous on a shared sales record (`AGENTS.md` standard 5).

## Consequences

- Mailbox credentials become deployment configuration.
- This is the first untrusted input path in the system. It is the reason ADR 0012
  hardens the AI boundary, and it needs the most adversarial tests in the plan.
- Silent drops need operator visibility — an ingestion log is required, not optional.
