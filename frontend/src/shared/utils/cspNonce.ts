/**
 * The Content-Security-Policy nonce for this page load, if the server gave us one.
 *
 * The policy is `style-src 'self' 'nonce-<random>'` with no `'unsafe-inline'`, so a
 * `<style>` element only applies if it carries that nonce. PrimeReact creates its component
 * styles at runtime (since 10.6 `primereact.min.css` ships empty), so it needs the nonce to
 * put on each one. The web server writes a fresh value into the page's
 * `<meta name="csp-nonce">` on every response, and the same value into the policy header.
 *
 * Returns undefined when there is no usable nonce: the Vite dev server and the unit tests,
 * where no policy is enforced and none is needed, and a page served without the server's
 * substitution, where the placeholder is still in place. PrimeReact then injects its styles
 * without a nonce, which is exactly right when there is no policy to satisfy.
 */

export const CSP_NONCE_META_NAME = 'csp-nonce';

/** What index.html ships with; the server swaps it for the real value. */
export const CSP_NONCE_PLACEHOLDER = '__CSP_NONCE__';

export const readCspNonce = (doc: Document = document): string | undefined => {
  const content = doc
    .querySelector(`meta[name="${CSP_NONCE_META_NAME}"]`)
    ?.getAttribute('content')
    ?.trim();
  if (!content || content === CSP_NONCE_PLACEHOLDER) return undefined;
  return content;
};
