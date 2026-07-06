/**
 * Shared error handling utilities for Masters module.
 * Centralises 422 backend error mapping and toast error handling.
 *
 * Requirements: 12.1, 12.4, 12.5, 12.6, 12.7
 */

/**
 * Maps 422 backend validation errors to react-hook-form field errors via `setError()`.
 *
 * The backend returns 422 responses with a `detail` array in the format:
 * `[{ loc: ["body", "field_name"], msg: "Error message" }]`
 *
 * This utility extracts the last segment of `loc` (the field name) and sets
 * a server-type error on that field in the form.
 *
 * @param error - The Axios error response (or any error with response.data.detail)
 * @param setError - The `setError` function from react-hook-form's `useForm()`
 */
export function mapBackendErrors(
  error: any,
  setError: (name: any, error: { type: string; message: string }) => void
): void {
  const details = error?.response?.data?.detail;
  if (Array.isArray(details)) {
    details.forEach(({ loc, msg }: { loc: string[]; msg: string }) => {
      const fieldName = loc[loc.length - 1];
      setError(fieldName, { type: 'server', message: msg });
    });
  }
}

/**
 * Standard toast error messages for common HTTP status codes.
 * Used to provide consistent error messaging across all master pages.
 */
export const ERROR_MESSAGES = {
  GENERIC_SERVER_ERROR: 'An unexpected error occurred. Please try again.',
  FORBIDDEN: "You don't have permission to perform this action.",
  NOT_FOUND: 'Record not found. It may have been deleted.',
} as const;

/**
 * Extracts a user-friendly error message from a backend error response.
 * Handles 400/409 (business rule / conflict) by returning the detail message,
 * and 500 by returning a generic message.
 *
 * @param error - The Axios error response
 * @returns An object with severity and message for Toast display
 */
export function getToastErrorInfo(error: any): { severity: 'error' | 'warn'; summary: string; detail: string } {
  const status = error?.response?.status;
  const rawDetail = error?.response?.data?.detail;

  if (status === 400 || status === 409) {
    const detail = typeof rawDetail === 'string'
      ? rawDetail
      : Array.isArray(rawDetail)
        ? rawDetail.map((e: any) => e.msg || e.message || String(e)).join('; ')
        : 'A conflict or validation error occurred.';
    return { severity: 'error', summary: 'Error', detail };
  }

  if (status === 403) {
    return { severity: 'error', summary: 'Forbidden', detail: ERROR_MESSAGES.FORBIDDEN };
  }

  if (status === 404) {
    return { severity: 'error', summary: 'Not Found', detail: ERROR_MESSAGES.NOT_FOUND };
  }

  // 500 or any other unhandled status
  return { severity: 'error', summary: 'Error', detail: ERROR_MESSAGES.GENERIC_SERVER_ERROR };
}
