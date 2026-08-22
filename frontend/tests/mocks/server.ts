/**
 * MSW server for Node (Vitest runs in Node, not a browser — there is no
 * Service Worker, so `setupServer` patches the request-issuing modules
 * directly instead).
 *
 * Started/reset/stopped from `tests/setup.ts` so every test file gets a
 * clean handler set: individual tests layer extra handlers on with
 * `server.use(...)`, and `resetHandlers` in `afterEach` guarantees one
 * test's override never leaks into the next.
 */

import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

/**
 * Default handlers, present unless a test overrides them with `server.use(...)`
 * (MSW checks per-test `.use()` handlers before these).
 *
 * `/auth/refresh` is answered here because `apiClient`'s request interceptor
 * silently calls it whenever a request goes out with no access token in
 * memory — the normal state at the start of any test, since `storageService`
 * is a fresh module per test file. Without a default, every RBAC/masters
 * test that renders a self-loading hook would otherwise trigger a real
 * "unhandled request" error on `/auth/refresh` before `apiClient`'s own
 * catch swallows it — noisy, and unrelated to what most of those tests are
 * actually checking. Tests that exercise the refresh flow itself (success,
 * failure, dedup — see `apiClient.test.ts`) override this per test.
 */
const defaultHandlers = [
  http.post('/api/v1/auth/refresh', () =>
    HttpResponse.json({
      access_token: 'test-access-token',
      token_type: 'Bearer',
      expires_in: 1800,
    }),
  ),
  // Same rationale for the RBAC self-loaders: `useApiPermissions`/`useCan`/
  // `useHasPermission` all dispatch `fetchApiPermissions` on mount whenever
  // the store's `isApiLoaded` is false, and `useFieldPermissions` dispatches
  // its own fetch per resource. A test asserting the synchronous "not loaded
  // yet" state still triggers that background request; these no-op defaults
  // (empty grants) let it resolve quietly instead of failing as unhandled.
  // A test that cares about the *result* of one of these fetches overrides
  // it with `server.use(...)`.
  http.get('/api/v1/rbac/my-permissions/api', () =>
    HttpResponse.json({ codes: [], resource_actions: {}, permissions: [] }),
  ),
  http.get('/api/v1/rbac/my-permissions/menu', () =>
    HttpResponse.json({ menu_keys: [], permissions: [] }),
  ),
  http.get('/api/v1/rbac/my-permissions/fields/:resource', ({ params }) =>
    HttpResponse.json({ resource: params.resource, fields: {} }),
  ),
];

export const server = setupServer(...defaultHandlers);
