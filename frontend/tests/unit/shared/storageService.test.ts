import { afterEach, describe, expect, it } from 'vitest';

import { storageService } from '@shared/services/storageService';

/**
 * `storageService` holds the access token in a module-level variable, not in
 * component state — so a value set by one test is still there for the next
 * unless it is explicitly cleared. `afterEach` resets it here rather than
 * relying on every test to remember to.
 */
describe('storageService', () => {
  afterEach(() => {
    storageService.clearAccessToken();
  });

  it('has no token and reports unauthenticated before anything is set', () => {
    expect(storageService.getAccessToken()).toBeNull();
    expect(storageService.isAuthenticated()).toBe(false);
  });

  it('stores and returns the token that was set', () => {
    storageService.setAccessToken('token-123');

    expect(storageService.getAccessToken()).toBe('token-123');
    expect(storageService.isAuthenticated()).toBe(true);
  });

  it('overwrites a previously stored token', () => {
    storageService.setAccessToken('first');
    storageService.setAccessToken('second');

    expect(storageService.getAccessToken()).toBe('second');
  });

  it('clears the token and reports unauthenticated again', () => {
    storageService.setAccessToken('token-123');
    storageService.clearAccessToken();

    expect(storageService.getAccessToken()).toBeNull();
    expect(storageService.isAuthenticated()).toBe(false);
  });
});
