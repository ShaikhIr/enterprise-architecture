import { describe, expect, it } from 'vitest';

import { extractApiError } from '@shared/utils/apiError';

/**
 * `extractApiError` unwraps the three shapes the backend can return:
 *   1. Domain errors from the exception middleware: `{ message, correlation_id }`.
 *   2. FastAPI validation errors: `{ detail: PydanticError[] }`.
 *   3. A plain string `detail`.
 * Anything else (network error, no response body) falls back to the caller's
 * default message.
 */
describe('extractApiError', () => {
  it('returns the fallback when the error has no response body', () => {
    const error = new Error('Network Error');

    expect(extractApiError(error, 'Something went wrong')).toBe('Something went wrong');
  });

  it('returns the fallback when the error is not an axios-shaped object', () => {
    expect(extractApiError('a plain string', 'fallback')).toBe('fallback');
    expect(extractApiError(null, 'fallback')).toBe('fallback');
    expect(extractApiError(undefined, 'fallback')).toBe('fallback');
  });

  it('prefers the domain error message over detail', () => {
    const error = {
      response: {
        data: { message: 'Country already exists', detail: 'ignored', correlation_id: 'abc' },
      },
    };

    expect(extractApiError(error, 'fallback')).toBe('Country already exists');
  });

  it('returns a string detail when there is no message', () => {
    const error = { response: { data: { detail: 'Not authenticated' } } };

    expect(extractApiError(error, 'fallback')).toBe('Not authenticated');
  });

  it('flattens a single Pydantic validation error with its field path', () => {
    const error = {
      response: {
        data: {
          detail: [{ loc: ['body', 'code'], msg: 'field required' }],
        },
      },
    };

    expect(extractApiError(error, 'fallback')).toBe('code: field required');
  });

  it('joins multiple Pydantic validation errors and drops the "body" location segment', () => {
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'code'], msg: 'field required' },
            { loc: ['body', 'name'], msg: 'string too short' },
          ],
        },
      },
    };

    expect(extractApiError(error, 'fallback')).toBe('code: field required; name: string too short');
  });

  it('falls back to "Invalid value" when a Pydantic error has neither msg nor message', () => {
    const error = { response: { data: { detail: [{ loc: ['body', 'code'] }] } } };

    expect(extractApiError(error, 'fallback')).toBe('code: Invalid value');
  });

  it('omits the field prefix when loc is absent on a Pydantic error', () => {
    const error = { response: { data: { detail: [{ msg: 'unexpected error' }] } } };

    expect(extractApiError(error, 'fallback')).toBe('unexpected error');
  });

  it('falls back when detail is an empty array', () => {
    const error = { response: { data: { detail: [] } } };

    expect(extractApiError(error, 'fallback')).toBe('fallback');
  });

  it('falls back when the response data is an empty object', () => {
    const error = { response: { data: {} } };

    expect(extractApiError(error, 'fallback')).toBe('fallback');
  });
});
