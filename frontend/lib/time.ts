/**
 * The two boundaries every timestamp crosses.
 *
 * The API stores and returns fixed-width UTC ISO-8601 ("2026-09-06T14:30:00Z")
 * — see `backend/app/time_utils.py`, where the format is load bearing because
 * timestamps are TEXT and every comparison is lexicographic. Browser
 * `datetime-local` inputs are always local wall-clock time. So values are
 * converted on the way in and on the way out rather than passed through.
 */

export function parseTimestamp(value: string): Date {
  const normalized = value.replace(" ", "T");
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(normalized);
  return new Date(hasZone ? normalized : `${normalized}Z`);
}

export function toLocalInput(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function toDateTimeInput(value: string): string {
  return toLocalInput(parseTimestamp(value));
}

export function nowDateTimeInput(): string {
  return toLocalInput(new Date());
}

export function localInputToUtc(value: string): string {
  return `${new Date(value).toISOString().slice(0, 19)}Z`;
}

export function formatTimestamp(value: string): string {
  return parseTimestamp(value).toLocaleString();
}
