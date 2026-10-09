# Phase 4 review packet — Tasks and Attachments

Branch: `autopilot/phase-4`. Depends on the `phase-3-accepted` tag (present).
This packet puts the phase into `AWAITING_REVIEW`.

Read time budget: 20-30 minutes (brief §3.5).

---

## 1. What changed

Phase 4's stated goal (`docs/ROADMAP.md`): *capture the two artifacts a deal
actually produces — the next action and the document.* User-visible outcome:
"call them back Thursday" is a task with a date that appears in My Tasks and on
the dashboard, and the proposal is attached to the entry that records sending
it.

Nine milestones: **4.1** the task model and its eight routes, **4.1b** the three
task screens, **4.2** the `follow_up_date` migration, **4.2a** the checkpoint
rework, **4.3** attachments, **4.3a** attaching from the composer, **4.4** the
export manifest, and the human's "build both" ruling as **4.5** a task's
discussion and **4.6** more than one person on a task. Per-milestone detail is
in `docs/autopilot/PROGRESS.md`; this is the plain-language summary.

### Tasks (§8)

- **A task is a title, an assignee, a due date, a done state and optionally the
  entry that prompted it** — and deliberately not a task manager. Written in the
  deal's sidebar (`TaskPanel`), worked through at `/tasks` or `g t`
  (`TasksPage` — the key documented and inert since 2.4a), counted in one line
  on the dashboard (`TaskSummary`).
- **The done state is `completed_at`/`completed_by`**, not a boolean, so the row
  answers when and who; both `POST .../complete` and `.../reopen` are idempotent
  through `COALESCE`, so the first completer is the one recorded.
- **The assignee may close a task they did not write** (**D-142**, which you
  ruled on): `PATCH` stays author-or-owner like every other edit, and the done
  state additionally accepts the assignee. It is the one place in this app where
  a row's own column widens who may change it.
- **My Tasks is the one task read that spans opportunities**, so its permission
  filter is inside the query — a task can be assigned to somebody before they
  are shared on the deal, and losing the share takes the task off their list
  rather than leaking the deal's name through it.
- **Undated tasks sort last**, in the display *and* in the keyset cursor,
  because a cursor over a different order than the one drawn skips rows.

### The follow-up migration (4.2)

- Revision `0010` converts every entry's `follow_up_date` into a task: title
  prefixed `Follow up:`, the entry's author as both author and assignee, and the
  **entry's** timestamps rather than the migration's clock. The column stays and
  keeps its values; it is dropped in Phase 6.
- **The composer's "Follow up" field is gone** (**D-144**). Keeping it was the
  worst of the three options: the column would go on accepting dates that
  nothing reads, so every new follow-up would be invisible.
- The calendar's second layer moved with it — `GET /api/v2/timeline/follow-ups`
  is replaced by `GET /api/v2/tasks?assignee=any&from=&to=`, one route with a
  filter rather than two over the same rows.

### Attachments (§6, ADR 0008)

- **A file hangs off the entry it belongs to**, uploaded and read on the entry
  card, with the picker collapsed behind "Attach file".
- **The stored path is the file's own SHA-256** (`{root}/{sha256[:2]}/{sha256}`),
  so identical uploads are one file on disk and a retried upload is idempotent.
  This replaced Phase F's random generated name (**D-147**).
- **The bytes decide what a file is.** Nothing the client declares is consulted,
  which is what makes a `.exe` renamed `.pdf` a 415. PDF, PNG, JPEG, GIF, text,
  and — new, and yours to rule on — Word, Excel and PowerPoint (**D-150**), with
  macro-carrying archives refused.
- **Downloading is a read of the opportunity**, so a viewer may and an outsider
  gets the ordinary 404. It is the only way bytes leave the volume: `/data` is
  never a static path, and a test walks four plausible ones to prove it.
- **Deleting one is soft, audited and undoable, and never removes the file**
  (**D-149**).

### Attaching where a person writes (4.3a)

4.3 put the control on the posted card, which is where a file is *read*. The
reviewer looked in the composer twice, and that is where a proposal is
actually to hand, so `TimelineEntryForm` carries **Attach a file (optional)**
in both modes while the card keeps its trigger for the file that arrives
later. The entry must exist before a file can hang off it, so a refused upload
leaves a **saved entry and an open form** saying exactly that, with the created
id held so a retry retries the file rather than posting a second entry. A
system entry offers no trigger, the way it offers no Edit or Delete.

### A task's discussion (4.5)

Flat and chronological: body, author, time (**D-162**). Not threaded, not
resolvable, not reactable, and **immutable** like every other comment here — so
no edit control, no `updated_at`, no version table. Reusing `comments` would
have broken `SearchResultPublic.entry_id` or left task comments unsearchable,
across the seventeen places `comments.note_id` is assumed; mirroring milestone
3.3 was more than was asked for. A comment tells the two people the task is
about and never the writer.

### More than one person on a task (4.6)

`task_assignees` is the truth; the API takes `assignee_emails` and answers with
`assignees` (**D-163**, and the breaking-changes table). **D-142 now reads "any
assignee may close it"** — a shared task is done when whoever got to it says
so, while editing stays author-or-owner. The **version snapshot records a set**
as a canonical `assignee_ids` string, because `version_is_current` compares
snapshots as strings; `apply_version` cannot write it back, since a set is a
table, so `VersionedTable` gained `applied_fields` and the route puts the set
back itself. `tasks.assignee_id` is frozen and dropped in Phase 6 beside
`follow_up_date`.

### The export manifest (4.4)

- One section at the end of the PDF (**D-154**): filename, size, uploader, date,
  and the entry each file hangs off — **listed, not embedded**, which the
  document says in its own words, and absent entirely when there are no files.
- **All three formats carry the files** (**D-155**), because one read feeds them.

---

## 2. How to try it

The structured version is the test page, which saves your marks and notes where
I read them back: **https://claude.ai/code/artifact/4458fb0b-658d-42e9-889f-e5bdca94f365**

`http://localhost:8000` — your own account, Gavin and Maximilian on
`password`. Bring a real proposal or contract off your own disk; that is the
point of this run.

1. **Attach a document to the entry it belongs to.** Open a deal, find the entry
   where a proposal went out, press *Attach file*. Try a `.docx` as well as a
   PDF.
2. **Try to get something past it.** Rename a binary to `.pdf` and attach it;
   then try a type that is not on the list at all. Both are refused on their
   bytes, with the server's own sentence.
3. **Check who can read it.** Download your own file; sign in as Gavin (a
   colleague on the deal) and as Maximilian (on nothing at all).
4. **Remove one and change your mind.** Delete an attachment, use the Undo in the
   toast, then read the deal's *Activity*: the removal and the restore are both
   there. While you are there, delete a task and look again — that row used to
   read "removed a colleague's access".
5. **Export the deal.** CSV or JSON from the timeline panel: the files are rows
   and fields now. The PDF's manifest needs the container (WeasyPrint), so it is
   the one line of this that your host gate checks rather than your laptop.
6. **Write and close a task.** Assign one to Gavin *and yourself* with a date in
   the past, sign in as them, find it at `/tasks`, tick it off. Either of you
   can close it and neither can rewrite it, which is D-142 read against a set.
7. **Talk about a task.** Press *Comment* on one and write what happened. The
   notification names the task, and reaches its author and assignees only.

---

## 3. Decisions needing review

Ten entries in `docs/autopilot/DECISIONS.md` are flagged for you. Four are
still open from the mid-phase checkpoint; six are new with attachments.

| | What I decided | What you might prefer |
|---|---|---|
| **D-146** | Comments on a task and multiple assignees are **deferred**, on §8's "deliberately not a task manager" | Build either; both were asked for |
| **D-148** | An attachment hangs off an entry as a **foreign key**, not ADR 0008's generic `entity_type`/`entity_id` | The polymorphic shape, if files should later hang off notes or comments |
| **D-150** | **Word, Excel and PowerPoint** are on the allowlist, separated by the archive's part prefix; macros refused | PDF and images only, narrower attack surface |
| **D-151** | Attachments are **invisible to the AI** — a filename is attacker-controlled text and an injection path | Let the model name the documents; needs a prompt change and an injection test |
| **D-152** | Filenames are **not searchable**, which answers the rowid-ceiling note from your 1.4 review rather than widening it | Make files findable by name; a small milestone of its own |
| **D-153** | The upload size cap refuses what gets **stored**, not what gets **received** — accepted risk | Close it with a request-size middleware |
| **D-154** | The manifest is **one section at the end**, each row naming its entry | A block on every entry, mirroring the screen |
| **D-155** | **All three** export formats carry the files, not only the PDF | PDF only, as the milestone line says |
| **D-156** | Next bumped 16.3.4 → **16.3.8** for a critical advisory; **five dev-only highs have no upstream fix** | Separate the bump from the feature work; record a Definition-of-Done exception for the five |
| **D-161** | Attaching exists in **two** places — the composer and the card | One of them, if the other reads as clutter |
| **D-162** | A task's discussion is **flat**: no reply, resolve or reaction | Threads, which is additive |
| **D-163** | Any **one** assignee may close a shared task | Author and owner only, or all assignees agreeing |
| **D-142** | (already accepted) the assignee may close a task they did not write | — |

---

## 4. Quality evidence

See `docs/autopilot/COVERAGE.md`'s Phase 4 gate entry for the full output. In
brief: the sandbox half of the split gate is green, and the Docker half is
yours to run (`scripts/autopilot-gate.sh 4`).

**Five findings this phase came from somewhere other than a passing test:**

- **The review was run against a build that did not contain the feature**
  (D-157). The reviewer's "I can't find the attach button" was correct: their
  container predated attachments by a day, and I had asked for a hands-on
  check without saying the app has to be rebuilt first. The fix is procedural:
  a review request names the build it needs.
- **A refused upload called itself a server error** (D-160) — a 415 with
  `code: "internal_error"`, because this is the first endpoint here that can
  answer 413 or 415 and neither had a name in the envelope. Twenty tests cover
  those refusals, every one asserting the status and the sentence and none the
  code. Found by posting a renamed executable at the real container.
- **4.6 broke 4.5's notification**, by leaving it reading `tasks.assignee_id` —
  the column 4.6 had just stopped writing — so a comment silently stopped
  reaching assignees. The unit test beside it passed because it never covered
  an assignee who is not the author; `e2e/24-tasks.spec.ts` is what failed. A
  frozen column is a hazard for as long as anything still reads it.

- **The activity log reported a deleted task as a revoked share.** A `default`
  branch in `lib/activity.ts` answered for whatever was added next, so
  `task_deleted` read as "removed a colleague's access" from the moment 4.1
  shipped it. The branch is gone; a missing case is now a build failure. This is
  the second catch-all in two sessions to answer for something added later — the
  first was the task edit that read "changed Assignee id".
- **4.1 shipped `PATCH /api/v2/tasks/{id}` with nothing calling it**, so the
  panel offered Delete and no way to change a title, a date or an assignee — and
  shipped four editable fields with **no edit history**, which `AGENTS.md`
  invariant 8 already required. You found both before any test did. Fixed in
  4.2a with `task_versions`, the fourth table of `versioning.py`'s shape.
- **Two of my own tests proved nothing.** 4.1's cascade test passed with the
  cascade removed (the read it asserted against filters deleted deals anyway),
  and 4.2's migration re-run guard broke the moment a later revision added a
  column. Both rewritten, both confirmed to fail against the unfixed code.

---

## 5. Risks and known limitations

- **The rendered PDF is verified now, but only in the container.** Run inside
  the image on 2026-10-09: 30 entries and 10 files give a 6-page, 110 KB PDF
  carrying the manifest; the same deal with no files is 63 KB with no manifest
  section at all. `test_pdf_export_produces_a_real_pdf` is still the suite's
  one skip on a Mac, so this stays a container question rather than a laptop
  one.
- **Attachment bytes are not backed up and never pruned.** ADR 0011 snapshots
  the database; uploads join that story in Phase R (R.5), which is also where a
  pruner for deleted files belongs, because the safe predicate has to consider a
  soft-deleted row and a restorable backup (D-149). A restored database can name
  files the volume has never held — the download answers 404 and says so.
- **The upload size cap is enforced after the parser has buffered the request**
  (D-153). An authenticated caller can fill the container's temp directory.
- **Five dev-only high advisories have no upstream fix** (D-156). Nothing ships
  to production; the fix does not exist yet.
- **No virus scanning**, as ADR 0008 already records as an accepted risk.

---

## 6. Out-of-scope items noticed, logged not built

- Comments on a task and multiple assignees (D-146) — asked for, deferred.
- Searchable attachment filenames (D-152), which would widen ADR 0007's rowid
  encoding. The fourth slot is still free.
- Live `?entry=` links in the AI's answers, which `PROGRESS.md` has carried
  since 3.9 and which needs a real model call to verify rather than a mocked one.
- A request-size middleware (D-153), which belongs beside the other request
  controls in `security.py` rather than inside a feature.

---

## 7. Preview of next phase

**Phase 6 — Custom Fields, Dashboards, Automations** follows this one directly,
since email moved to v3 (D-141). It is the phase to meet deliberately: 6.3's
automation rules write to your data **on a timer**, which is the first thing in
this app that acts with nobody clicking, and 6.5 brings the scheduler that makes
that possible (and finally gives `make backup` a schedule).
