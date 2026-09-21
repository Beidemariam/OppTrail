import type { ReactNode } from "react";

import { entryTypeLabel, type EntryType } from "../lib/domain";

/**
 * One glyph per entry type, milestone 2.6. `docs/DESIGN-SYSTEM.md`'s
 * accessibility section is explicit that colour is never the sole carrier of
 * meaning, so the badge below pairs each type's existing colour with a shape
 * a colour-blind reader can also tell apart. Hand-drawn rather than a new
 * dependency (`lucide-react` et al.) — eleven glyphs do not justify a
 * package, and the project has no icon library to stay consistent with
 * (nothing under `app/` used `<svg>` before this).
 */
const ICON_PATHS: Record<EntryType, ReactNode> = {
  call: (
    <>
      <rect x="7" y="2" width="10" height="20" rx="2" />
      <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  email: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <polyline points="3 7 12 13 21 7" />
    </>
  ),
  meeting: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <circle cx="17" cy="9" r="2.2" />
      <path d="M15 20c0-2.2 1.8-4 4-4" />
    </>
  ),
  demo: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <line x1="8" y1="20" x2="16" y2="20" />
      <line x1="12" y1="16" x2="12" y2="20" />
    </>
  ),
  proposal: (
    <>
      <path d="M6 2h9l5 5v15H6z" />
      <line x1="9" y1="12" x2="16" y2="12" />
      <line x1="9" y1="16" x2="16" y2="16" />
    </>
  ),
  contract: (
    <>
      <path d="M6 2h9l5 5v15H6z" />
      <polyline points="9 13 11 15 15 10" />
    </>
  ),
  stage_change: (
    <>
      <line x1="4" y1="12" x2="18" y2="12" />
      <polyline points="13 6 19 12 13 18" />
    </>
  ),
  other: (
    <>
      <circle cx="6" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="18" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </>
  ),
  site_visit: (
    <>
      <path d="M12 21s7-7.5 7-12a7 7 0 1 0-14 0c0 4.5 7 12 7 12z" />
      <circle cx="12" cy="9" r="2.5" />
    </>
  ),
  objection: (
    <>
      <path d="M12 3 2 20h20L12 3z" />
      <line x1="12" y1="10" x2="12" y2="15" />
      <circle cx="12" cy="18" r="0.5" fill="currentColor" stroke="none" />
    </>
  ),
  competitor_intel: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
};

/** Decorative: the label sitting beside it in `EntryTypeBadge` already names
 * the type, so a screen reader does not need to announce the glyph too. */
export function EntryTypeIcon({ type }: { type: EntryType }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="entry-type-icon"
    >
      {ICON_PATHS[type]}
    </svg>
  );
}

export function EntryTypeBadge({ type }: { type: EntryType }) {
  return (
    <span className={`type-badge ${type}`}>
      <EntryTypeIcon type={type} />
      {entryTypeLabel(type)}
    </span>
  );
}
