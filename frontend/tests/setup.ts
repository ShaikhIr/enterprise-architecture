/**
 * Global Vitest setup, loaded once via `vite.config.ts`'s `test.setupFiles`.
 *
 * - Extends Vitest's `expect` with the jest-dom matchers (`toBeVisible`,
 *   `toHaveTextContent`, ...).
 * - Cleans up whatever Testing Library rendered after every test, so one
 *   test's DOM never leaks into the next.
 * - Polyfills the browser APIs PrimeReact components reach for that jsdom
 *   does not implement (ResizeObserver, matchMedia, IntersectionObserver).
 *   Without these, mounting a DataTable/Dropdown/Dialog throws before the
 *   test under it even runs.
 */

import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';

import { server } from './mocks/server';

// `onUnhandledRequest: 'error'` fails a test loudly the moment it issues a
// request no handler covers, rather than letting it hang until axios's own
// 30s timeout — the default would let a missing handler masquerade as a
// slow network instead of a test bug.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

afterEach(() => {
  cleanup();
});

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

class IntersectionObserverStub {
  root: Element | null = null;
  rootMargin = '';
  thresholds: ReadonlyArray<number> = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
vi.stubGlobal('IntersectionObserver', IntersectionObserverStub);

// jsdom implements `window.matchMedia` as `undefined`; PrimeReact's responsive
// helpers call it unconditionally on mount.
vi.stubGlobal(
  'matchMedia',
  vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
);

// jsdom does not implement scrollIntoView; PrimeReact's Dropdown/overlay
// panels call it when highlighting the active option.
Element.prototype.scrollIntoView ??= vi.fn();

/**
 * jsdom has no layout engine, so `offsetParent` is always `null` — there is
 * no box model to determine an offset parent from. PrimeReact's overlay
 * positioning (`DomHandler.absolutePosition`, used by Dropdown, MultiSelect,
 * Calendar, ...) branches on `element.offsetParent` to decide how to measure
 * a freshly-opened panel: when it is `null`, `getHiddenElementDimensions()`
 * measures by briefly flipping `display` to `block` and back to `none` —
 * leaving the panel hidden afterwards, since jsdom never reaches the branch
 * that keeps it visible. Every option inside is then invisible to Testing
 * Library's role/text queries, even though the click that opened it worked.
 * Stubbing `offsetParent` to the element's parent (a reasonable value for a
 * visible, non-fixed-position element) sends PrimeReact down the
 * `element.offsetWidth/offsetHeight` branch instead, which jsdom does let
 * reach the "not hidden" outcome.
 */
Object.defineProperty(HTMLElement.prototype, 'offsetParent', {
  get() {
    return this.parentNode;
  },
  configurable: true,
});
