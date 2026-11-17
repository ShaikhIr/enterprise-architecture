/**
 * Turns an axios error from the workflow endpoints into one readable line.
 *
 * The backend speaks two error shapes: domain failures come back as
 * `{ success, message, correlation_id }` from the exception middleware, while
 * validation failures are FastAPI's `detail` — either a string or an array of
 * Pydantic error objects. All three are flattened here so pages do not each
 * re-implement the unwrapping.
 */

interface PydanticError {
  msg?: string;
  message?: string;
  loc?: (string | number)[];
}

interface ErrorBody {
  message?: string;
  detail?: string | PydanticError[];
}

/**
 * Seconds the server asked the caller to wait, from a `Retry-After` header that holds a
 * number of seconds. Null when the header is absent or is anything else (this API never
 * sends the HTTP-date form).
 */
export const getRetryAfterSeconds = (error: unknown): number | null => {
  const headers = (error as { response?: { headers?: Record<string, unknown> } })?.response
    ?.headers;
  const raw = headers?.['retry-after'];
  const seconds = typeof raw === 'string' || typeof raw === 'number' ? Number(raw) : NaN;
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null;
};

/** A wait as people say it: "less than a minute", "about a minute", "about 15 minutes". */
export const formatWait = (seconds: number): string => {
  if (seconds < 60) return 'less than a minute';
  const minutes = Math.ceil(seconds / 60);
  return minutes === 1 ? 'about a minute' : `about ${minutes} minutes`;
};

export const extractApiError = (error: unknown, fallback: string): string => {
  const body = (error as { response?: { data?: ErrorBody } })?.response?.data;
  if (!body) return fallback;

  if (typeof body.message === 'string' && body.message) return body.message;

  const { detail } = body;
  if (typeof detail === 'string' && detail) return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const field = item.loc?.filter((part) => part !== 'body').join('.');
        const text = item.msg ?? item.message ?? 'Invalid value';
        return field ? `${field}: ${text}` : text;
      })
      .join('; ');
  }

  return fallback;
};
