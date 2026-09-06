# OppTrail v2 — Information Architecture and UX Specification

Companion to `DESIGN-SYSTEM.md`. This describes structure and behaviour; that
describes tokens and components.

## Principles

1. **The timeline is the product.** Every other view is a way of getting back to a
   timeline. When a design decision is contested, the one that makes the timeline
   clearer wins.
2. **The URL is the state.** Opportunity, view, filters, grouping and selection all
   live in the URL, which is what makes saved views, deep links, the back button and
   "send me that screen" work at all. None of these are possible today.
3. **Keyboard first.** Every action reachable without a mouse. This is why people
   prefer one tool over another for work they do fifty times a day.
4. **Never block on a write.** Optimistic by default, undo instead of confirm.
5. **Density is a feature.** Show more, not bigger.

## Navigation shell

```
┌──────────────────────────────────────────────────────────────────────┐
│ OppTrail   [⌘K Search or jump to…]              🔔 3    ● User ▾     │ TopBar
├────────────┬─────────────────────────────────────────────────────────┤
│ Dashboard  │                                                         │
│ Pipeline   │                    Route outlet                         │
│ My Tasks   │                                                         │
│ Search     │                                                         │
│ ─────────  │                                                         │
│ SAVED VIEWS│                                                         │
│  My open   │                                                         │
│  Stalled   │                                                         │
│  Closing   │                                                         │
│ ─────────  │                                                         │
│ RECENT     │                                                         │
│  Acme Exp. │                                                         │
└────────────┴─────────────────────────────────────────────────────────┘
```

Sidebar is collapsible to icons and remembers its state. Saved views are the
primary navigation object — the sidebar is a list of questions the user asks
repeatedly, not a list of features.

### Routes

| Route | Screen |
|---|---|
| `/` | Dashboard |
| `/pipeline?view=board&group=stage&filter=…` | Multi-view over opportunities |
| `/opportunities/:id` | Opportunity detail, timeline view |
| `/opportunities/:id/:view` | `timeline` \| `notes` \| `tasks` \| `files` \| `activity` |
| `/tasks` | My Tasks across opportunities |
| `/search?q=…` | Global search results |
| `/settings/fields` \| `/notifications` \| `/automations` | Admin and preferences |

Filters and grouping serialize to the query string. A saved view is a stored
query string plus a name.

## Opportunity detail

The most important screen. Three regions, independently scrollable:

```
┌───────────────────────────────────────────────────────────────────────┐
│ ← Pipeline / Acme Expansion                          [Export ▾] [⋯]   │
│ Acme Corp · $250,000 · Closes 12 Mar        [Negotiation ▾] ⚠ Stalled │
│ Owner: Beide · Shared with 3 · Custom fields inline                    │
├──────────────────────────────────┬────────────────────────────────────┤
│ [Timeline] Notes Tasks Files Log │  AI Assistant              [Ask]   │
│                                  │  ────────────────────────────────  │
│ [Search] [Type▾] [Author▾] [Date]│  Where do we stand?                │
│                                  │                                    │
│ ┃ ● Mar 3  Call · Beide          │  Deal is in negotiation with       │
│ ┃   Pricing pushback             │  procurement. Two objections…      │
│ ┃   └ Note · Sara  2 comments ▾  │  [Entry #41] [Entry #47]           │
│ ┃                                │                                    │
│ ┃ ○ Mar 1  Stage → Negotiation   │  ────────────────────────────────  │
│ ┃   system                       │  Suggested next actions            │
│                                  │  · Follow up with procurement      │
│ [+ Log an entry]                 │    [Create task]                   │
└──────────────────────────────────┴────────────────────────────────────┘
```

- **Header** is sticky and holds the facts a rep needs constantly: value, stage,
  close date, owner, stalled state. Stage is an inline editable dropdown; changing
  it writes through the existing endpoint and auto-logs a system entry.
- **Timeline** is a vertical rail with type-coloured, icon-bearing markers. System
  entries render hollow and muted — visibly distinct from authored content, which
  the current UI already does and should keep.
- **Notes collapse to a summary line** with a comment count. This is the single
  biggest density win over the current UI, where every note and every comment is
  always fully expanded.
- **AI sidebar** is collapsible and remembers its state per user. Citations are
  clickable and scroll the timeline to the entry.
- **Composer is always reachable** at the bottom of the timeline, expanding into
  the rich editor on focus.

### The entry composer

Progressive disclosure. Collapsed it is one line: "Log an entry". On focus it
expands to type selector, title, rich body, timestamp (defaulting to now), and
type-specific custom fields. `⌘Enter` saves, `Esc` collapses with a draft kept.

Drafts persist locally per opportunity — losing a half-written call note to a
mis-click is the kind of thing that stops people logging calls.

## Views

One view switcher, one filter bar, five renderers over the same query.

| View | Row/card shows | Primary interaction |
|---|---|---|
| **Timeline** | Entry tree (default, per opportunity) | Read, add, expand |
| **Board** | Card: name, account, value, close date, stalled | Drag between stage columns |
| **List** | Dense row, grouped, expandable | Scan, inline edit |
| **Table** | Selectable columns incl. custom fields | Inline edit, bulk select |
| **Calendar** | Close dates and follow-ups | Drag to reschedule |

The filter bar is shared: chips for active filters, an "Add filter" combobox, and a
grouping selector. Changing a filter updates the URL; saving prompts for a name.

Board and table both virtualize — 400 opportunities is well past what unvirtualized
DOM handles comfortably.

## Interaction patterns

### Command palette (⌘K)

The keyboard entry point to everything: fuzzy-jump to an opportunity, switch view,
run an action on the current context, or fall through to full-text search. Opens on
`⌘K` from anywhere including inside inputs.

### Keyboard map

| Key | Action |
|---|---|
| `⌘K` | Command palette |
| `g` then `d`/`p`/`t` | Go to Dashboard / Pipeline / Tasks |
| `c` | Create — opportunity on list views, entry on an opportunity |
| `/` | Focus filter/search |
| `j` / `k` | Move selection down / up |
| `x` | Toggle selection (bulk) |
| `e` | Edit focused item |
| `⌘Enter` | Submit any composer |
| `Esc` | Collapse, close, or clear selection |
| `?` | Shortcut reference |

### Optimistic updates and undo

Every mutation applies immediately, reconciles on response, and rolls back with an
explanatory toast on failure. Destructive actions **do not confirm** — they apply
and offer Undo for 10 seconds.

This is a deliberate reversal of what was shipped in the last review cycle, where
confirmations were added to five destructive actions. Confirm dialogs were correct
then, because there was no undo and no audit visibility. With soft deletes already
in place, undo is a real `deleted_at = NULL`, and an undo toast is both faster and
safer than a modal people learn to dismiss reflexively. Opportunity deletion keeps
its typed confirmation — it cascades across an entire record, and that one deserves
friction.

### Bulk actions

Multi-select in list and table via checkbox, `x`, or shift-click range. An action
bar replaces the filter bar while a selection is active: change stage, assign owner,
add to view, export, delete. Bulk operations are one request, transactional, and
report per-item failures rather than failing wholesale.

## Notifications

Bell opens a panel; the panel links to a full inbox at `/notifications`.

Grouped by opportunity, then by type: "3 new comments on Acme Expansion". Unread
carry a dot; read stay visible and filterable — the current implementation returns
unread only, so marking one read makes it unreachable forever.

Per-type, per-channel preferences live in settings, with digest frequency.

## Onboarding and empty states

A new user's dashboard is not blank. It shows one card explaining what an
opportunity is, a Create button, and a link to import from CSV. The first
opportunity's timeline shows its auto-generated "Opportunity created" entry with a
prompt to log the first real one.

## Responsive behaviour

Desktop-first, degrading rather than reflowing into a separate mobile design
(**[ASSUMPTION]**, Q5).

- **≥1280px** — full shell, AI sidebar open.
- **1024-1280px** — AI sidebar collapses to a tab.
- **768-1024px** — nav sidebar collapses to icons; table view drops to list.
- **<768px** — single column, bottom nav, board becomes a stage-filtered list.
  The one flow that must stay genuinely good at this width is **logging an entry**,
  since that is what a rep does from a phone after a call.
