# 0012. Keep the AI read-only by construction; treat all context as untrusted

Status: Accepted (v2)

## Context

The agent is read-only **by construction**: `routes_ai.py` assembles timeline text,
calls the model, and returns a string. No tool is exposed, so there is no write path
to misuse — a property `AGENTS.md` requires explicitly ("never give it a
write-capable tool, even behind a confirmation step").

`ai_service.py:134` interpolates timeline content directly into the model input with
no delimiting. Today the blast radius is small: content comes only from users who
already have write access, and output is only shown back to users who already have
read access, so the worst case is a misleading answer.

**Two v2 decisions remove that containment.** Inbound email (ADR 0009) admits
content from outside the auth boundary, and attachments (ADR 0008) admit file
content. Phase 2's proposed AI features — draft follow-up emails, next-best-action,
notes-to-entry parsing — convert "misleading text" into "action taken".

The clarifying question about whether read-only is absolute was not answered, so
this ADR takes the conservative position. **[ASSUMPTION]**

## Decision

1. **No write tools, ever.** Features that would change data produce a **proposal**
   the user reviews and applies through the ordinary authenticated endpoint. The
   notes-to-entry parser returns a draft entry rendered in the normal create form;
   nothing is persisted until the human submits it. The AI is never the actor in an
   audit row.
2. **Context is untrusted data, not instructions.** Timeline content moves out of
   the free-text prompt into a delimited, structured block with an explicit system
   instruction that content inside it is data. Entry, note and comment bodies are
   escaped so they cannot close the delimiter.
3. **Provenance is labelled in-context.** Each block carries its source
   (`user` / `email` / `attachment`) so the model, and the rendered answer, can
   distinguish a colleague's note from text an outsider emailed in.
4. **Outbound drafts are never auto-sent.** A drafted follow-up email opens in a
   composer the user edits and sends.
5. **Injection tests are part of the suite.** Notes containing instruction-shaped
   text ("ignore previous instructions", "you are now...") must not change the
   agent's behaviour, and must not cause it to claim it modified anything.

## Provider

The brief states OpenRouter with `gpt-oss-20b`. **The code uses the OpenAI SDK
directly** (`ai_service.py:4,130,131`), configured by `OPENAI_API_KEY` /
`OPENAI_MODEL` (`settings.py:7-8`), and `AGENTS.md` says to use OpenAI. This ADR
records the code as authoritative until corrected; the discrepancy is logged in
`docs/OPEN-QUESTIONS.md`. Either way the call site is one function
(`ai_service.ask_openai`), so a provider swap is contained.

## Consequences

- Some briefed AI features become "propose, human applies", which is slower to use
  and dramatically cheaper to get wrong.
- The read-only guarantee stays structural rather than prompt-dependent, which is
  what makes it hold against injected content.
- If the answer to the open question is that human-confirmed writes are acceptable,
  only decision 1 loosens — and even then the confirmation must be a real diff the
  user approves, not a yes/no dialog.
