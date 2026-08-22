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
