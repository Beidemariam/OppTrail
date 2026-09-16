# Decisions Log

Format: `D-### | date | question | options | choice | reason | reversible (Y/N) | needs human review (Y/N)`

---

**D-001** | 2026-09-16 | `docs/v2_review_brief.md:14` says "OpenRouter (`gpt-oss-20b`)"; the code (`backend/app/ai_service.py:4,124-137`, `settings.py:7-8`), `AGENTS.md` ("OpenAI for AI calls"), and ADR 0012 all say OpenAI. | (a) leave the stale line, (b) fix it to match code/ADRs | (b) — replaced the line with "OpenAI (`OPENAI_API_KEY` / `OPENAI_MODEL`) for the AI agent" | Brief §1's source-of-truth hierarchy ranks code and ADRs above `v2_review_brief.md`; the brief's own §1 explicitly names this as a known stale item to fix in Phase F (§4.1.6). Already resolved once in `docs/OPEN-QUESTIONS.md` Q1. | Y | N — mechanical application of an already-settled hierarchy and an explicit brief instruction |

**D-002** | 2026-09-16 | WCAG version conflict: brief §7's capability list and §8 Phase R say "WCAG 2.1 AA"; `AGENTS.md`'s Quality Bar says "WCAG 2.2 AA, enforced by axe in Playwright"; `docs/ROADMAP.md` Phase 2 acceptance says "axe clean in CI" without naming a version. | (a) target 2.1 AA per the brief, (b) target 2.2 AA per `AGENTS.md` | (b) — treat 2.2 AA as the bar for every accessibility acceptance criterion in Phases 2 and R | Source-of-truth hierarchy (brief §1) ranks `AGENTS.md` above this brief. 2.2 AA is also a strict superset of 2.1 AA's success criteria, so targeting it never produces a criterion that fails a 2.1 audit. | Y | N — resolving a version conflict per the hierarchy the brief itself defines; no scope or architecture changes |

**D-003** | 2026-09-16 | Scope cross-check (brief §4.1.4): §7's capability list includes "design system with light/dark themes." `docs/DESIGN-SYSTEM.md:101-107` commits to "full parity from the start" for dark mode, but no phase in `docs/ROADMAP.md` states a dark-theme acceptance criterion — Phase 2's technical work only says "design tokens from DESIGN-SYSTEM.md, including the three corrected contrast values," which could be satisfied by tokens alone with no dark palette shipped. | (a) leave implicit inside "design tokens" work, (b) add an explicit dark-theme acceptance criterion, and pick a phase | Proposal only, per §4.1.4 — **not added to the plan.** Recommend adding to Phase 2 (where the token system and Radix primitives land, and where `DESIGN-SYSTEM.md` says retrofitting is expensive), with an explicit acceptance criterion: "light and dark themes both pass axe contrast checks on every shipped component." | `DESIGN-SYSTEM.md` treats retrofitting as the risk to avoid, so the phase that introduces the token system is the natural owner. Deferring it to Phase R risks exactly the two-pass audit `DESIGN-SYSTEM.md` warns against. | Y (adds a phase acceptance criterion) | **RESOLVED 2026-09-16 — ACCEPTED by the human.** Added to `docs/ROADMAP.md` Phase 2 acceptance: "Light and dark themes both ship, and both pass `axe` contrast checks on every component delivered in this phase." Phase 2 milestones in `PROGRESS.md` updated to match. No longer a proposal; it is now phase scope. |

**D-004** | 2026-09-16 | Reconnaissance found `backend/app/routes_opportunities.py` (`fetch_accessible_opportunity`, `fetch_owned_opportunity`, lines 86-132) re-implements role resolution inline instead of calling `permissions.py`'s `require_opportunity_access` / `require_opportunity_owner`, even though behavior currently matches (`test_opportunities.py:134` passes either way). Brief §4.5 explicitly asks for "one central permission-check function used by every service method touching an opportunity." | (a) leave the duplication since behavior is currently correct, (b) consolidate onto `permissions.py` as a Phase F milestone | (b) | This is exactly the gap §4.5 names, not a new judgment call — implementing it is in-scope for Phase F regardless. Logged here so the "why" survives into the milestone rather than being rediscovered. | Y | N — directly specified by the brief; no architecture change, just deduplication |

**D-005** | 2026-09-16 | `docs/code_review.md` finding 4a identified that editors could edit (not just fail to be blocked from deleting) any colleague's timeline entry or note, and recommended the reviewer "pick one and apply it consistently." Only the delete side was tightened (`require_delete_permission`, author-or-owner) — edit was left permissive. `AGENTS.md`'s permissions model states editors "add and edit freely" and is silent on restricting edits of others' content, while explicitly reserving deletion to the author or owner. Current code (`routes_timeline.py:340-383` for entries, `:513-577` for notes) matches this reading. | (a) tighten edit to author-or-owner to match delete, (b) keep edit permissive, matching the literal `AGENTS.md` wording and existing passing tests | (b) — keep current behavior; treat this as a deliberate, now-explicit reading of an ambiguous spec rather than an unresolved defect | `AGENTS.md` positively states editors edit freely; it does not say "except other people's items." Changing it would contradict `test_editor_can_write_and_viewer_is_read_only` (`test_timeline.py:225`) and would be scope the brief didn't ask for (brief §9: "no unnecessary defensive branches," and changing tested behavior needs a justified reason, not just discomfort with an old review comment). | Y | **RESOLVED 2026-09-16 — OVERRULED by the human.** Choice (a) is adopted: **editors may edit only their own content.** Edit permission now mirrors delete exactly — author or opportunity owner. `AGENTS.md`'s Permissions Model has been rewritten accordingly and, being above this brief in the §1 hierarchy, is the binding statement: "an editor who may not remove a colleague's record may not rewrite it either." This closes `docs/code_review.md` finding 4a the way it asked ("pick one and apply it consistently"). Implement as Phase F milestone **F.5a**; `test_editor_can_write_and_viewer_is_read_only` (`test_timeline.py:225`) is expected to change, and that change is authorised here rather than being a weakened assertion under brief §6.5. |

**D-006** | 2026-09-16 | How to structure Phase F's own milestone list, since §4.1 items 1-6 (inventory, baseline, roadmap conversion, scope cross-check, gap analysis, stale-reference fix) are tightly coupled and none alone produces an independently gate-able artifact. | (a) one milestone per numbered §4.1 bullet, (b) bundle all of §4.1 as milestone F.1 ("Reconnaissance"), with gap-analysis findings becoming their own later Phase F milestones per §4.1.5's instruction | (b) | §4.1.5 already says gap-analysis items "each become a Phase F milestone" — implying §4.1's other five items are the input to that split, not milestones in themselves. Splitting inventory from baseline-running from roadmap-conversion would produce milestones with no independent acceptance criterion. | Y | N — a session-planning choice, not a product or architecture decision |

**D-007** | 2026-09-16 | D-004's permission-check consolidation (`routes_opportunities.py` `PATCH`/`DELETE` now call `permissions.require_opportunity_owner` instead of an inline owner-only query) changes behavior for one untested edge case: a shared editor or viewer (who has read access but isn't the owner) now gets **403** on `PATCH`/`DELETE /api/opportunities/{id}`, where the old inline query returned **404** for any non-owner regardless of whether they had read access. No existing test exercised this case — `test_non_owner_cannot_view_or_mutate_opportunity` only covers a user with *no* share at all, where both old and new code agree on 404. | (a) preserve the old 404-for-any-non-owner behavior with an explicit branch, (b) accept the new 403-for-shared-non-owner behavior since it now matches `routes_sharing.py`'s owner-only endpoints, which already 403 a shared editor | (b) | `routes_sharing.py`'s `require_opportunity_owner` already returns 403, not 404, when a shared non-owner calls a share-management endpoint — the old inline query in `routes_opportunities.py` was the *inconsistent* one. 403 ("you can see this, but can't do that") is the correct status for a user with read access attempting a write action; 404 is reserved for "you have no access at all" per this codebase's own convention (CLAUDE.md's Permissions section). Preserving the old behavior via (a) would mean writing a second, deliberately-wrong permission check specifically to avoid a status-code change no test depended on — the opposite of what D-004 asked for. | Y | N — a bugfix that falls directly out of D-004's already-approved consolidation, not a new architectural choice. Added `test_shared_editor_can_view_but_not_mutate_opportunity` (`test_opportunities.py`) to lock the new behavior in, confirmed to fail against the pre-fix code per brief §6.5. |

**D-008** | 2026-09-16 | F.2 asks to verify `SESSION_SECRET` (`settings.py`, `.env.example`) is "either wired up or removed" (`docs/code_review.md` finding 10: it's declared but read nowhere; sessions use random `token_urlsafe` IDs, which need no signing key). ADR 0009 (Phase 5, inbound email) says HMAC-signed reply addresses will "finally give `settings.session_secret`... a real purpose, **or better, a dedicated `INBOUND_EMAIL_SECRET`**" — so the field has a *future* consumer, just not today's. | (a) leave it declared now so Phase 5 can reuse the name, (b) remove it now; Phase 5 introduces whatever secret its actual design needs | (b) | ADR 0009 itself prefers a dedicated `INBOUND_EMAIL_SECRET` over reusing `session_secret` — so keeping the field around doesn't even save Phase 5 a rename. Brief §9 forbids "unnecessary defensive branches," and AGENTS.md's coding standards say the same about dead code; a config value nothing reads is dead code. Removed from `settings.py`, `.env.example`, and `README.md`; added `environment` (`development`/`production`/`test`, fail-fast validated) in its place, which F.2's error-envelope work actually needs today (to decide whether to show exception detail to clients). | Y | N — removing genuinely dead configuration per an explicit brief instruction and the review finding's own recommendation; Phase 5 is free to name its own secret when ADR 0009 lands. |

**D-009** | 2026-09-16 | Standing up `mypy --strict` (F.2's tooling milestone) found 81 errors when run against `app/` + `tests/` together; the app-only subset was 28, all fixable with type annotations. Fixing all 81 (including annotating every test helper and fixture) is a much larger, lower-value undertaking than fixing the 28 in application code, since test helpers' types are usually inferrable from usage at call sites and mypy's main value is catching bugs in code that ships. | (a) run strict mypy over `app/` and `tests/` both, fix everything, (b) scope strict mypy to `app/` only for now, leave `tests/` unchecked | (b) | `[tool.mypy] files = ["app"]` in `backend/pyproject.toml` already scoped this way before the errors were even counted (a deliberate default, not a retroactive excuse) — mirrors how the brief separates "strict mypy" (§3.4, an application-code quality gate) from test-suite concerns. Revisit if a later phase wants typed test fixtures for a specific reason. | Y | N — a proportionality call for one milestone's tooling setup, not a permanent policy; reversible by deleting the `files` key. |

**D-010** | 2026-09-16 | F.3 flagged `AuditLogEntryPublic.detail` (previously `str` — the raw JSON blob was never even parsed before being wrapped in another JSON string on the wire) and `NotificationPublic.payload` (`dict[str, Any]`) as opaque. There are exactly 7 audit actions and 6 notification types, each writing a fixed, enumerable set of keys (`routes_sharing.py`, `routes_timeline.py`, `routes_opportunities.py`, `notification_service.py`). Two ways to type this: (a) give `detail`/`payload` a field-level type union (one Pydantic model per action/type, `Union[...]`, resolved by a lookup keyed on the sibling `action`/`type` field at construction time), or (b) restructure `AuditLogEntryPublic`/`NotificationPublic` themselves into whole-object discriminated unions (`Annotated[Union[...], Field(discriminator=...)]`), so the generated OpenAPI schema statically links `type` to `payload`'s shape and TypeScript can narrow one from the other. | (a) field-level union, resolved in Python before constructing the response model, or (b) whole-object discriminated union, doubling the number of top-level response schemas (13 new wrapper classes on top of the 13 payload/detail variant classes) | (a) | Both close the actual gap the milestone named — `detail`/`payload` are no longer `str`/`dict[str, Any]`, and the generated `frontend/lib/api-types.ts` now emits a real `oneOf`-style union for each. (b) is more precise (lets the frontend narrow `payload`'s type from `type` in one step) but doubles the schema surface for a benefit the frontend code doesn't need: the only two read sites (`notificationText`, the audit-log `<code>` block) either don't need narrowing at all (`JSON.stringify`) or narrow via a plain `"title" in payload` check, which TypeScript already supports on a flat union. Brief §9's "no speculative abstraction" and AGENTS.md's coding standards both weigh against building the more general shape for a consumer that doesn't exist yet. Revisit if a later phase's frontend work actually needs `type`-to-`payload` narrowing at the type level. | Y | N — a proportionality call on how far to take a typing improvement the brief already specified; not a scope or architecture change. |

**D-011** | 2026-09-16 | F.3's client-generation step (`scripts/generate-api-client.sh`, backed by `openapi-typescript`) needs a way to dump the FastAPI app's OpenAPI schema without starting a server. | (a) add a `/openapi.json`-scraping step that boots uvicorn and curls it, (b) a small `app/export_openapi.py` module that imports `app.main.app` and prints `app.openapi()` — no server, no network | (b) | `app.openapi()` is a plain method call against already-registered route metadata; booting a real server just to fetch a schema it can produce in-process adds a process lifecycle (start, wait-for-ready, kill) to what should be a sub-100ms build step, and risks flakiness in CI. Kept out of `main.py` itself so importing it never runs `configure_logging()`/`initialize_database()` (`main.py`'s `lifespan`). | Y | N — a build-tooling implementation choice with no behavioral or API surface effect. |

---

## Scope cross-check summary (brief §4.1.4)

Walked every item in brief §7 against `docs/ROADMAP.md` Phases 1-6:

| §7 capability | Roadmap coverage | Gap? |
|---|---|---|
| System-generated timeline entries | Shipped (v1) | No |
| Entry type tags with color/icon | Color shipped (v1); icons for 3 new types in Phase 2 | No (existing 8 types keep color-only; acceptable minor scope reading, not logged as a gap) |
| Note edit history | Shipped (v1, `note_versions`) | No |
| Audit log | Shipped (v1) | No |
| @mentions and in-app notifications | Shipped (v1) + reworked inbox in Phase 1 | No |
| Stalled flags and follow-up reminders | Stalled flag shipped (v1); Phase 6's automation acceptance criterion ("no-activity-for-14-days rule fires... creates a task... logs a system entry") is the reminder mechanism | No — confirmed this maps to journey §6.3 #9, not a separate unbuilt feature |
| CSV/JSON export (PDF retained) | Shipped (v1) | No |
| Rich text | Phase 3 (TipTap) | No |
| Custom fields | Phase 6 | No |
| Table/board/calendar views | Phase 2 (board, list guaranteed; table/calendar may slip to Phase 3 per the roadmap's own stated risk) | No — already an acknowledged, not hidden, risk |
| Saved and shareable filtered views | Phase 2 (`saved_views`) | No |
| Dashboards | Phase 6 | No |
| Real-time collaboration | Phase 3 (SSE, ADR 0003) | No |
| Opportunity-scoped automations | Phase 6 | No |
| Keyboard-first navigation and command palette | Phase 2 | No |
| Design system with light/dark themes | Tokens land in Phase 2; no explicit dark-theme acceptance criterion anywhere | **Yes — D-003** |
| WCAG 2.1 AA | Phase 2 + Phase R axe checks, version conflict with `AGENTS.md` | **Yes — D-002 (resolved by hierarchy, not a scope gap)** |

One proposal follows from this table (D-003); everything else is already covered
by name in the roadmap or resolved by the source-of-truth hierarchy.

---

## Human rulings — 2026-09-16

Recorded outside a phase gate because Phase F is `IN_PROGRESS`; brief §5 treats
decisions "recorded in DECISIONS.md or review feedback" as phase scope, so these
are binding on the remaining Phase F milestones.

| ID | Agent's choice | Human ruling | Effect |
|---|---|---|---|
| D-001 | Fix the OpenRouter reference | Upheld | Already done in F.1 |
| D-002 | WCAG 2.2 AA per `AGENTS.md` | Upheld | Binding for Phases 2 and R |
| D-003 | Proposal only, recommend Phase 2 | **Accepted** | Now a Phase 2 acceptance criterion |
| D-004 | Consolidate onto `permissions.py` | Upheld | Phase F milestone F.5 |
| D-005 | Keep edit permissive | **Overruled** | Editors edit own content only; F.5a |
| D-006 | Bundle §4.1 as one milestone | Upheld | No change |

Two operational rulings, for the record:

- **Sandbox egress stays minimal.** Claude Code's telemetry to
  `http-intake.logs.us5.datadoghq.com` and its updater's reach for
  `downloads.claude.ai` are both refused by `sandbox/proxy/allowlist.conf` and
  both are non-fatal. Leave them refused: the first is third-party telemetry, and
  the second reinforces the pinned `CLAUDE_CODE_VERSION`. Do not widen the
  allowlist to silence the retries.
- **The quality gate is split.** `make check` cannot run "Docker build + smoke
  test" inside the sandbox. Run every other item; the human runs
  `scripts/autopilot-gate.sh <ID>` on the host, and
  `scripts/autopilot-accept.sh` refuses a phase without its receipt. See brief
  §3.4 and `sandbox/README.md`.

---

## Human note — 2026-09-16 (F.2 review)

`make check-fast` assumes `frontend/node_modules` is already installed and fails
with `sh: 1: tsc: not found` when it is not. The sandbox gives the container its
own `node_modules` volume (so a container `npm ci` cannot overwrite the host's
native `@next/swc` and `sharp` builds), and that volume starts empty, so a clean
sandbox cannot run the gate at all.

**Action for a later F milestone (F.3 or the Phase R CI work, your choice):**
make the frontend targets install dependencies when they are missing — an
`npm ci` guarded on `node_modules` being absent, or a `deps` prerequisite — so
`make check-fast` and `make check` are runnable from a clean checkout. The Phase R
CI workflow will hit exactly this on its first run otherwise.

Not treated as an F.2 defect: the milestone's own gate genuinely passed, and this
was only exposed by a sandbox fix made after that run.
