/**
 * Date utility functions for handling dates without timezone issues.
 *
 * The Problem:
 * When JavaScript parses a date string like "2025-01-05", it interprets it as UTC midnight.
 * When displayed in a timezone west of UTC (like US Pacific), this becomes the previous day.
 *
 * The Solution:
 * Parse dates as local time by explicitly extracting year, month, day components.
 */

/**
 * Parse an ISO date string (YYYY-MM-DD) as a local Date object.
 * This prevents the timezone shift that occurs with new Date("YYYY-MM-DD").
 *
 * @param dateStr - Date string in YYYY-MM-DD format
 * @returns Date object in local time, or null if invalid
 */
export function parseLocalDate(dateStr: string): Date | null {
  if (!dateStr) return null;

  const parts = dateStr.split('-');
  if (parts.length !== 3) return null;

  const [year, month, day] = parts.map(Number);
  if (isNaN(year) || isNaN(month) || isNaN(day)) return null;

  // Create date using local time (month is 0-indexed)
  return new Date(year, month - 1, day);
}

/**
 * Format a date string for display without timezone shift.
 *
 * @param dateStr - Date string in YYYY-MM-DD format
 * @param options - Intl.DateTimeFormat options (optional)
 * @returns Formatted date string, or empty string if invalid
 */
export function formatDate(
  dateStr: string,
  options?: Intl.DateTimeFormatOptions
): string {
  const date = parseLocalDate(dateStr);
  if (!date) return '';

  return date.toLocaleDateString(undefined, options);
}

/**
 * Format a date string for display in short format (e.g., "1/5/2025").
 *
 * @param dateStr - Date string in YYYY-MM-DD format
 * @returns Formatted date string, or empty string if invalid
 */
export function formatDateShort(dateStr: string): string {
  return formatDate(dateStr);
}

/**
 * Format a date string for display in long format (e.g., "January 5, 2025").
 *
 * @param dateStr - Date string in YYYY-MM-DD format
 * @returns Formatted date string, or empty string if invalid
 */
export function formatDateLong(dateStr: string): string {
  return formatDate(dateStr, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Compare two date strings for sorting.
 * Returns negative if a < b, positive if a > b, 0 if equal.
 *
 * @param a - First date string in YYYY-MM-DD format
 * @param b - Second date string in YYYY-MM-DD format
 * @returns Comparison result
 */
export function compareDates(a: string, b: string): number {
  const dateA = parseLocalDate(a);
  const dateB = parseLocalDate(b);

  if (!dateA && !dateB) return 0;
  if (!dateA) return -1;
  if (!dateB) return 1;

  return dateA.getTime() - dateB.getTime();
}
