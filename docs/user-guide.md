# Using OppTrail

OppTrail is a timeline for sales opportunities. A deal is a record with a
history: every call, email, meeting and decision in the order it happened, with
notes and discussion hanging off the moments that need them. Everything else in
the app exists to get you back to that timeline.

This guide is written for the person using it, not the person running it —
`docs/operations.md` is the other one.

## Getting around

Six screens, in the rail down the left (it collapses, and remembers):

| Screen | What it is for |
|---|---|
| **Opportunities** | Every deal you can see, as a board, a list, a table or a calendar |
| **Tasks** | Everything owed by or to you, across every deal |
| **Reports** | Six numbers about the pipeline, computed live |
| **Automations** | Rules that do something when a condition is met |
| **Search** | One keyword across every deal, note, comment and filename |

`?` shows every keyboard shortcut. `Ctrl K` (or `Cmd K`) opens the command
palette, which jumps to any deal by name. `g` then `d`, `t`, `s` or `p` goes to
a screen without the mouse.

## A deal

Open one and the top band is the record — name, account, value, stage, close
date — and it stays there while you scroll. Click any of those values to edit
it in place; there is no separate edit form, and no Save button to forget.

Below it, the timeline, newest first. **New entry** writes the next thing that
happened: pick a type (call, email, meeting, demo, proposal, contract, site
visit, objection, competitor intel), give it a title and a body, and set the
date it *happened* — which is not the same as the date you typed it, and the
app keeps both.

Three things hang off an entry:

- **Notes** — a longer thought about that moment. Notes can be edited, and
  every edit is kept.
- **Comments** — a discussion on a note, one reply deep. Comments cannot be
  edited by anyone, including you: a conversation is a record. A thread can be
  **resolved**, which collapses it to "Resolved by …" with a Show beside it.
- **Attachments** — the proposal, the redlines, the signed contract. On the
  entry that records sending it.

Everything you write takes Markdown, with a toolbar for the common marks and
three typed triggers: `@` offers the people on this deal, `/` offers blocks
(heading, code, divider), and `#` offers this deal's own earlier entries and
links to the one you pick.

## Who can see what

Three roles, and no fourth:

- **Owner** — the person who created the deal, or whoever it was handed to.
  Can edit the record, share it, read its history, and delete it.
- **Editor** — can add entries, notes and comments freely, and change or delete
  only their own.
- **Viewer** — can read everything shared and write nothing.

Sharing is per deal, from the **Sharing** panel in a deal's rail. A deal you
have no access to answers as though it does not exist, which is deliberate:
existence itself is not public.

Handing a deal over leaves you on it as an editor rather than removing you,
because that is the one action with no undo available to the person doing it.

### Keeping something to yourself

Two different shapes, both on a deal:

- **A private entry.** New entries start private, with a tick box —
  *Reveal this entry to everyone on the deal* — to share one. A private entry
  still appears in your colleagues' timeline with its number, your name and
  its time, and nothing else; the content is yours. Nobody else can read it,
  **including the deal's owner**: "private unless the owner asks" is not
  private. Seal an entry you have already shared and the notifications it sent
  are withdrawn too. Unsealing does not re-send them.
- **My notes.** In the deal's rail, under Tasks: one notebook per person per
  deal, for the thinking that is not a record of anything that happened. It is
  not in the deal's history at all — not in search, not in an export, not in
  the AI's context, not in any report.

## Finding things

The board's **Filter and sort** button opens eight controls; what you applied
stays on screen as a chip you can remove one at a time. A filtered view lives
in the URL, so it can be bookmarked or sent to a colleague — and what they see
is still filtered by their own access, which is why two people can apply the
same saved view and get different rows.

**Saved views** name a filter set. A shared one publishes its *name* to
everyone signed in; its results stay per reader.

**Search** covers entries, notes, comments and attachment filenames across
every deal you can read, and a result takes you to the exact thing it matched,
not just the deal.

## Tasks

A follow-up can be written on the entry that prompted it, and it carries a due
date, a description and more than one assignee if it needs them. Any assignee
can tick it off — a shared task is done when whoever got to it says so. Tasks
have their own discussion, flat and chronological.

`/tasks` is everything across every deal, grouped by what is late, what is
coming up and what is done.

## Reports

Six numbers at `/reports`, computed from the live data every time you open it:
pipeline by stage, win rate, average time in stage, the stalled list (nothing
for a fortnight), activity per person, and a weighted forecast.

Two of them will sometimes say **not measured** rather than zero. That is a
different claim: a win rate with nothing closed yet is unknown, not 0%, and
average time in stage is only correct back to the first stage change this
database recorded.

## Automations

A rule is one trigger, a flat list of conditions, and one action. Five
triggers — a stage change, a new entry, a field change, nothing happening for
N days, a close date approaching — and four actions: create a task, notify
someone, add an entry, change the stage.

The screen reads the rule back to you as a sentence while you build it. **Run**
previews it without writing anything (that is the default); untick the dry run
to let it act. Everything a rule does is attributed to you and shows up in the
deal's timeline naming the rule, and the run log keeps every match including
the ones it declined and why.

A rule can only ever do one thing: nothing a rule writes can trigger another
rule.

## Asking the AI

**Ask** on a deal opens a drawer. It reads that deal's timeline and answers
from it, streaming as it goes, and cites entries by the `#number` printed on
each card so you can check it. You can scope a question to a date range, and
the answer will say so rather than claiming something never happened when it
merely did not happen in June.

Two things it cannot do. It **cannot write anything** — the database connection
it uses refuses writes, so this is a property of the plumbing rather than a
promise in a prompt. And it cannot read inside an attachment; it knows a file's
name, size and who uploaded it, and it will tell you so if you ask what a
document says.

A reader with no access to a deal cannot ask about it, and a private entry is
absent from the context of everyone except its author.

## Exports

Three formats per deal — PDF, CSV, JSON — plus CSV and JSON for a selection
from the board. The PDF is the deal as a document: the record, the whole
timeline, notes, comments, and a list of the attachments with sizes and
uploaders. Files are listed, not embedded.

## Undo

Almost nothing in this app asks "are you sure". Deleting an entry, a note, a
comment or an attachment happens immediately and leaves a toast with **Undo**
for ten seconds; an undone delete restores exactly what that delete took,
including replies to a comment.

Deleting a whole opportunity is the exception and asks you to type its name,
because it takes the timeline with it.

Nothing is ever really deleted, and an edit never overwrites what it replaced:
a deal's **Activity** dialog is where the history lives — who changed what and
when, with the previous version of any edited field and a Restore beside it.
