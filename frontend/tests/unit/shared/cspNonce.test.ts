/**
 * Tests for readCspNonce.
 *
 * The page's Content-Security-Policy has no 'unsafe-inline' for styles, so PrimeReact's
 * runtime <style> elements only apply with the per-response nonce the web server writes into
 * <meta name="csp-nonce">. Getting this wrong is silent in the wrong direction: a nonce that
 * is read when it should not be, or missed when it is there, shows up as an unstyled app.
 */

import { afterEach, describe, expect, it } from 'vitest';

import { CSP_NONCE_PLACEHOLDER, readCspNonce } from '@shared/utils/cspNonce';

const setMeta = (content: string | null) => {
  document.head.querySelectorAll('meta[name="csp-nonce"]').forEach((el) => el.remove());
  if (content === null) return;
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'csp-nonce');
  meta.setAttribute('content', content);
  document.head.appendChild(meta);
};

afterEach(() => setMeta(null));

describe('readCspNonce', () => {
  it('returns the value the server wrote into the page', () => {
    setMeta('4f9d1c0e7a2b43d6a1f0b8c5e9d27a31');

    expect(readCspNonce()).toBe('4f9d1c0e7a2b43d6a1f0b8c5e9d27a31');
  });

  it('ignores surrounding whitespace', () => {
    setMeta('  abc123  ');

    expect(readCspNonce()).toBe('abc123');
  });

  it('is undefined when the page has no nonce tag (dev server, tests)', () => {
    setMeta(null);

    expect(readCspNonce()).toBeUndefined();
  });

  it('is undefined while the placeholder is still in place', () => {
    // The page was served without the server's substitution: there is no policy to satisfy,
    // and the placeholder must never be handed to PrimeReact as if it were a real nonce.
    setMeta(CSP_NONCE_PLACEHOLDER);

    expect(readCspNonce()).toBeUndefined();
  });

  it('is undefined for an empty or blank value', () => {
    setMeta('');
    expect(readCspNonce()).toBeUndefined();

    setMeta('   ');
    expect(readCspNonce()).toBeUndefined();
  });

  it('reads from the document it is given', () => {
    const other = document.implementation.createHTMLDocument('x');
    const meta = other.createElement('meta');
    meta.setAttribute('name', 'csp-nonce');
    meta.setAttribute('content', 'from-other-document');
    other.head.appendChild(meta);

    expect(readCspNonce(other)).toBe('from-other-document');
  });
});
