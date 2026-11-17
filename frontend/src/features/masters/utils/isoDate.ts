/**
 * Conversion between the backend's `date` columns and PrimeReact's Calendar.
 *
 * `effective_date` is a calendar date, not an instant, so it must never go through
 * `toISOString()`: that converts to UTC first, and for any timezone ahead of UTC a
 * local midnight becomes the previous day. In IST (+05:30), picking 1 Jan would be
 * stored as 31 Dec. Formatting from the local parts avoids the shift entirely.
 */

const pad = (value: number): string => String(value).padStart(2, '0');

/** Format a picked date as `yyyy-MM-dd`, reading local calendar parts. */
export const toIsoDate = (value: Date | null | undefined): string | null => {
  if (!value) return null;
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
};

/** Parse a `yyyy-MM-dd` string into a local Date for the Calendar. */
export const fromIsoDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return null;
  // Constructed from parts rather than `new Date(string)`, which parses a
  // date-only string as UTC midnight and then renders in local time.
  return new Date(year, month - 1, day);
};

/** Display a stored ISO date as `dd-MM-yyyy`, or an em dash when absent. */
export const formatIsoDate = (value: string | null | undefined): string => {
  const parsed = fromIsoDate(value);
  if (!parsed) return '—';
  return `${pad(parsed.getDate())}-${pad(parsed.getMonth() + 1)}-${parsed.getFullYear()}`;
};

/**
 * Display a stored timestamp as `dd-MM-yyyy`, dropping the time.
 *
 * Separate from `formatIsoDate` because the two inputs are different shapes and the wrong
 * one fails silently rather than loudly: `formatIsoDate` splits on "-", so a timestamp's
 * `14T10:39:06+00:00` day part parses as NaN and the whole column renders as em dashes.
 * A column of em dashes reads as missing data, not as a formatting bug, which is exactly
 * the kind of mistake that survives review.
 *
 * Parsed rather than sliced, so the date shown is the one in the reader's own timezone. A
 * submission stored at 20:00 UTC happened on the following day in IST, and slicing the
 * first ten characters would report the UTC day instead.
 */
export const formatTimestampDate = (value: string | null | undefined): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return `${pad(parsed.getDate())}-${pad(parsed.getMonth() + 1)}-${parsed.getFullYear()}`;
};
