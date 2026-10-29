/**
 * Tests for ContentViewerDialog's JSON highlighting.
 *
 * The highlighter builds its markup as a string. A Content-Security-Policy without
 * 'unsafe-inline' refuses `style="…"` attributes that arrive that way, so the colours have to
 * come from classes. These tests pin that down, because a regression is silent in tests (jsdom
 * enforces no policy) and only shows in a browser, as an uncoloured dialog and a CSP error.
 */

import { describe, expect, it } from 'vitest';

import { ContentViewerDialog } from '@shared/components/ContentViewerDialog';

import { renderWithProviders, screen } from '../../test-utils';

const renderJson = (json: string) =>
  renderWithProviders(
    <ContentViewerDialog visible onHide={() => undefined} title="Details" content={json} />,
  );

/** The <pre> the highlighter fills by string injection. */
const highlighted = (): HTMLElement => {
  const pre = screen.getByRole('dialog').querySelector('pre');
  if (!pre) throw new Error('no highlighted <pre> rendered');
  return pre as HTMLElement;
};

describe('ContentViewerDialog — JSON highlighting', () => {
  const json = JSON.stringify({ name: 'alice', count: 3, active: true, note: null });

  it('colours with classes, one per kind of token', () => {
    renderJson(json);

    const pre = highlighted();
    expect(pre.querySelector('.em-json-key')).toHaveTextContent('"name"');
    expect(pre.querySelector('.em-json-string')).toHaveTextContent('"alice"');
    expect(pre.querySelector('.em-json-number')).toHaveTextContent('3');
    expect(pre.querySelectorAll('.em-json-literal')).toHaveLength(2); // true, null
  });

  it('puts no style attribute in the injected markup', () => {
    renderJson(json);

    // The CSP refuses these when they arrive as a string. (React's own style props are
    // applied through the CSSOM, which the policy allows, so only the spans matter.)
    expect(highlighted().querySelectorAll('span[style]')).toHaveLength(0);
    expect(highlighted().innerHTML).not.toMatch(/style\s*=/i);
  });

  it('still escapes markup in the data rather than injecting it', () => {
    renderJson(JSON.stringify({ field: '<img src=x onerror=alert(1)>' }));

    const pre = highlighted();
    expect(pre.querySelector('img')).toBeNull();
    expect(pre).toHaveTextContent('<img src=x onerror=alert(1)>');
  });
});
