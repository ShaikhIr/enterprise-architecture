/**
 * Unit tests for shared error handling utilities.
 * Tests mapBackendErrors and getToastErrorInfo functions.
 *
 * Validates: Requirements 12.4, 12.5, 12.6
 */

import { describe, it, expect, vi } from 'vitest';
import { mapBackendErrors, getToastErrorInfo, ERROR_MESSAGES } from '../../src/features/masters/utils/errorUtils';

describe('mapBackendErrors', () => {
  it('maps 422 detail array to form field errors via setError', () => {
    const setError = vi.fn();
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'entity_name'], msg: 'Field is required' },
            { loc: ['body', 'short_code'], msg: 'Must be at most 50 characters' },
          ],
        },
      },
    };

    mapBackendErrors(error, setError);

    expect(setError).toHaveBeenCalledTimes(2);
    expect(setError).toHaveBeenCalledWith('entity_name', { type: 'server', message: 'Field is required' });
    expect(setError).toHaveBeenCalledWith('short_code', { type: 'server', message: 'Must be at most 50 characters' });
  });

  it('handles nested loc arrays by taking last element', () => {
    const setError = vi.fn();
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'lines', '0', 'product_master_id'], msg: 'Required field' },
          ],
        },
      },
    };

    mapBackendErrors(error, setError);

    expect(setError).toHaveBeenCalledWith('product_master_id', { type: 'server', message: 'Required field' });
  });

  it('does nothing when detail is not an array', () => {
    const setError = vi.fn();
    const error = {
      response: {
        data: {
          detail: 'Some string error message',
        },
      },
    };

    mapBackendErrors(error, setError);

    expect(setError).not.toHaveBeenCalled();
  });

  it('does nothing when error has no response', () => {
    const setError = vi.fn();

    mapBackendErrors(null, setError);
    mapBackendErrors(undefined, setError);
    mapBackendErrors({}, setError);

    expect(setError).not.toHaveBeenCalled();
  });

  it('handles empty detail array gracefully', () => {
    const setError = vi.fn();
    const error = {
      response: {
        data: {
          detail: [],
        },
      },
    };

    mapBackendErrors(error, setError);

    expect(setError).not.toHaveBeenCalled();
  });
});

describe('getToastErrorInfo', () => {
  it('returns error detail for 400 status with string message', () => {
    const error = {
      response: {
        status: 400,
        data: { detail: 'Business rule violation' },
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe('Business rule violation');
  });

  it('returns error detail for 409 status with string message', () => {
    const error = {
      response: {
        status: 409,
        data: { detail: 'Entity with this name already exists' },
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe('Entity with this name already exists');
  });

  it('joins array detail messages for 409 status', () => {
    const error = {
      response: {
        status: 409,
        data: {
          detail: [
            { msg: 'Duplicate vendor code' },
            { msg: 'Email already in use' },
          ],
        },
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe('Duplicate vendor code; Email already in use');
  });

  it('returns forbidden message for 403 status', () => {
    const error = {
      response: {
        status: 403,
        data: {},
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe(ERROR_MESSAGES.FORBIDDEN);
  });

  it('returns not found message for 404 status', () => {
    const error = {
      response: {
        status: 404,
        data: {},
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe(ERROR_MESSAGES.NOT_FOUND);
  });

  it('returns generic message for 500 status', () => {
    const error = {
      response: {
        status: 500,
        data: {},
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe(ERROR_MESSAGES.GENERIC_SERVER_ERROR);
  });

  it('returns generic message for unknown status codes', () => {
    const error = {
      response: {
        status: 503,
        data: {},
      },
    };

    const result = getToastErrorInfo(error);

    expect(result.severity).toBe('error');
    expect(result.detail).toBe(ERROR_MESSAGES.GENERIC_SERVER_ERROR);
  });
});
