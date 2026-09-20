# OppTrail v2 — Design System

Extends the existing palette in `AGENTS.md` into a token set. The target is
ClickUp-level information density: dense but not cramped, legible at a glance.

## Contrast audit of the current palette

Measured, not assumed. Three in-use pairs fail WCAG AA for text:

| Pair | Where | Ratio | AA text |
|---|---|---|---|
| Slate `#6B7280` on background `#F7F9FB` | body meta text | 4.58 | Pass |
| Navy `#0B2540` on background | headings | 14.71 | Pass |
| Dark `#2F2300` on amber `#F2A93B` | proposal badge (`globals.css:750`) | 7.72 | Pass |
| **Teal `#0F9D8C` on white** | link text (`globals.css:89,808`) | **3.38** | **Fail** |
| **Red `#D64545` on white** | error text (`globals.css:231,246`) | **4.38** | **Fail** |
| **White on red `#D64545`** | notification badge (`globals.css:266`) | **4.38** | **Fail** |

**The brand colours are sound as fills and unsafe as text.** The fix is not to
change the brand but to add darkened text variants, keeping the originals for
backgrounds, borders and markers.

| Token | Value | Ratio on white | Use |
|---|---|---|---|
| `--teal-600` | `#0B7C6E` | 5.09 | Link and accent **text** |
| `--teal-500` | `#0F9D8C` | 3.38 | Fills, borders, timeline markers |
| `--red-600` | `#B33838` | 5.93 | Error **text**, badge fills carrying white text |
| `--red-500` | `#D64545` | 4.38 | Destructive fills with dark text |
| `--green-600` | `#227A3A` | 5.37 | Closed Won **text** |
| `--amber-600` | `#8A5A00` | 5.93 | Warning **text** |

Rule: **a colour token is either a text token or a fill token, never both.**

**As built (milestone 2.5).** The tokens below live in `frontend/app/globals.css`
and the audit above is re-run on every test run by `frontend/lib/contrast.test.ts`,
which reads that file and measures every pair the app paints, in both palettes.
Building it found one more failure than the table records: slate `#6B7280` passes
on the app background (4.58) and **fails on the sunken surface `#EEF2F6`** (4.30),
which is where the stage columns, the sharing panel and the AI sidebar put it. The
`--text-secondary` role is therefore `#5C6673` — 5.18 on sunken, 5.83 on white.

## Tokens

### Colour semantics

Never reference a brand colour directly in a component; reference a role.

```
--bg-app        #F7F9FB     --text-primary    #0B2540
--bg-surface    #FFFFFF     --text-secondary  #5C6673 (see above)
--bg-sunken     #EEF2F6     --text-inverse    #FFFFFF
--bg-hover      #F0F4F8     --text-link       var(--teal-600)
--bg-selected   #E6F4F2     --text-danger     var(--red-600)
--border-subtle #E3EAF0     --border-strong   #D9E2EA
--focus-ring    #0B7C6E     (4.5:1+ against every surface token; verified)
```

Stage colours are a scale, not arbitrary: Prospecting → Negotiation runs cool to
warm, Closed Won green, Closed Lost red. **Never colour alone** — every stage and
entry type also carries an icon and a text label, which is both an accessibility
requirement and a density win.

### Spacing — 4px base

`space-0.5 = 2` · `1 = 4` · `2 = 8` · `3 = 12` · `4 = 16` · `6 = 24` · `8 = 32` ·
`12 = 48`

Dense UI lives in the 4-12px range. Anything above 24px inside a data view is
usually a layout mistake.

### Typography

System font stack — no webfont, which keeps the 250 KB bundle budget reachable and
removes a render-blocking request. `ui-monospace` for IDs, timestamps and values.

| Token | Size / line-height | Use |
|---|---|---|
| `text-xs` | 11 / 16 | Metadata, timestamps, table density mode |
| `text-sm` | 13 / 18 | **Default for data views** |
| `text-base` | 15 / 22 | Body copy, note content |
| `text-lg` | 18 / 24 | Section headings |
| `text-xl` | 22 / 28 | Page title |
| `text-2xl` | 28 / 34 | Opportunity name |

Weights: 400, 500 (emphasis in dense rows), 700 (headings). Numerals are tabular in
tables and value columns so figures align.

### Radii, elevation, motion

Radii: `sm 4` (inputs, badges) · `md 8` (cards, panels) · `lg 12` (modals) ·
`full` (avatars, pills).

Elevation is four steps only — flat, raised (cards), overlay (dropdowns, popovers),
modal. Borders do most of the work; shadow is reserved for things that genuinely
float.

Motion: `fast 120ms` (hover, focus), `base 180ms` (dropdowns, expand), `slow 260ms`
(drawers, modals), all `ease-out`. Everything respects
`prefers-reduced-motion: reduce`, which is not optional in a drag-and-drop UI.

### Density modes

*Not built yet — D-075 defers both modes to the milestone that builds the table
view they exist for (2.8). The token set that carries them is in place.*

Two, user-switchable, as a root token change rather than per-component variants:

- **Comfortable** — 40px rows, `text-sm`. Default.
- **Compact** — 30px rows, `text-xs`, tighter cells. For the table view and power
  users.

### Dark mode

Full parity from the start, because retrofitting means auditing every component
twice. Semantic tokens make it a palette swap; keep the same contrast floors, and
re-run the audit on the dark palette rather than assuming inversion preserves it.
Note that saturated teal and amber need *lightening* on dark backgrounds, so the
`-600` text variants above have `-300` counterparts.

## Component inventory

Built once, used everywhere. Each ships with its empty, loading, error and
permission-denied state — those are part of the component, not an afterthought.

**Primitives** — Button (primary/secondary/ghost/danger), IconButton, Input,
Textarea, Select, Combobox, DatePicker, DateTimePicker, Checkbox, Radio, Switch,
Badge, Avatar, Tooltip, Spinner, Skeleton.

**Composites** — Dialog (focus-trapped, replacing every `window.confirm`),
Drawer, Popover, DropdownMenu, ContextMenu, Toast (with undo action), Tabs,
Accordion, Breadcrumb, Pagination, EmptyState, ErrorState, ConfirmDialog.

**Domain** — OpportunityCard, StageBadge, EntryTypeBadge, TimelineEntry,
NoteBlock, CommentThread, MentionText, RichTextEditor, RichTextViewer,
AttachmentChip, FilterBar, FilterChip, SavedViewMenu, ViewSwitcher, ColumnPicker,
UserPicker, TaskRow, NotificationItem, AuditRow, StalledBadge, AiMessage,
CommandPalette.

**Layout** — AppShell, Sidebar, TopBar, PageHeader, SplitPane, VirtualList.

`VirtualList` is load-bearing at 400 opportunities and 200-entry timelines; every
long list routes through it.

### Library choice

*As built (2.5): `Dialog` and `AlertDialog` are adopted, behind
`app/Modal.tsx` and `app/ConfirmDialog.tsx`. Each further primitive arrives with
the milestone that has a caller for it (D-073).*

**Headless primitives from Radix UI**, styled with the tokens above. Radix supplies
the focus management, keyboard interaction and ARIA wiring that the current app has
none of — one `aria`/`role` attribute in 1,829 lines. Writing an accessible
combobox, dialog and menu by hand is weeks of work to arrive somewhere worse.

Rejected: a full component kit (MUI, Ant, Chakra) — they bring their own design
language and fighting it costs more than styling headless parts.

## State designs

Treated as first-class, because they are most of what a user sees on a slow day.

| State | Design |
|---|---|
| **Empty (no data yet)** | Explain what this view holds and the one action to fill it. Never a bare "No results." |
| **Empty (filtered to nothing)** | Distinguish from above — say which filters are active and offer to clear them |
| **Loading, first paint** | Skeletons matching final layout, never a centred spinner — spinners make dense views feel slower than they are |
| **Loading, refetch** | Keep stale content visible, show a subtle top progress bar. Never blank out data that is still valid |
| **Optimistic pending** | Show the change immediately at reduced opacity; reconcile or roll back with a toast |
| **Error, recoverable** | Inline, next to the thing that failed, with a Retry. **Not** the current single global banner in a sidebar far from the action |
| **Error, validation** | Field-level, from the API's `fields` map — the current client flattens every 422 to "Request failed" |
| **Permission denied** | Explain the role required and who owns the opportunity. Never a dead-end 403 |
| **Offline** | Banner, queue mutations, replay on reconnect |

## Accessibility

Baseline **WCAG 2.2 AA**, enforced by `axe` assertions in Playwright rather than a
one-off audit.

- Visible focus ring on every interactive element, 3:1 against both adjacent
  surfaces.
- Full keyboard operability, including drag-and-drop, which needs a keyboard
  alternative (move-to-stage from a menu). This is the requirement most likely to be
  skipped and the one that makes the board view unusable without a mouse.
- Real dialogs with focus trap and restore.
- Live regions for toasts, save confirmations and AI streaming.
- Icons paired with text or `aria-label`; colour never the sole carrier of meaning.
- Respect `prefers-reduced-motion` and `prefers-contrast`.
