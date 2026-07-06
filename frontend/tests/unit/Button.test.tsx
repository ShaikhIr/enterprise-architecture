/**
 * Unit tests for the Button component — Emcure Design System
 *
 * Requirements covered: 4.1–4.13
 *
 * CSS module class names: Vitest is configured with css.modules.classNameStrategy
 * set to 'non-scoped', which causes CSS Modules to return non-hashed, human-readable
 * class names in the test environment. This allows us to assert on class names by
 * their source keys (e.g. 'primary', 'btn', 'disabled', 'sm').
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import React from 'react';
import Button, { type ButtonVariant } from '../../src/shared/components/ui/Button/Button';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns the button element rendered by the component.
 */
function renderButton(props: Partial<React.ComponentProps<typeof Button>> & { children?: React.ReactNode } = {}) {
  const { getByRole } = render(
    <Button {...props}>{props.children ?? 'Click me'}</Button>
  );
  return getByRole('button');
}

// ---------------------------------------------------------------------------
// 1. Default variant
// ---------------------------------------------------------------------------

describe('Button — default variant', () => {
  it('renders with "primary" class when no variant prop is provided', () => {
    const btn = renderButton();
    expect(btn.className).toContain('primary');
  });

  it('renders with base "btn" class always', () => {
    const btn = renderButton();
    expect(btn.className).toContain('btn');
  });

  it('defaults to type="button"', () => {
    const btn = renderButton();
    expect(btn.getAttribute('type')).toBe('button');
  });
});

// ---------------------------------------------------------------------------
// 2. Variant rendering — each variant applies its CSS module class
// ---------------------------------------------------------------------------

describe('Button — variant class application', () => {
  const colorVariants: ButtonVariant[] = [
    'primary',
    'secondary',
    'ghost',
    'danger',
    'save',
    'delete',
  ];

  it.each(colorVariants)(
    'variant "%s" renders with the "%s" CSS class',
    (variant) => {
      const btn = renderButton({ variant });
      expect(btn.className).toContain(variant);
    },
  );

  it('variant "sm" renders with the "sm" CSS class', () => {
    const btn = renderButton({ variant: 'sm' });
    expect(btn.className).toContain('sm');
  });
});

// ---------------------------------------------------------------------------
// 3. sm size modifier
// ---------------------------------------------------------------------------

describe('Button — sm size modifier', () => {
  it('applies the "sm" class when variant is "sm"', () => {
    const btn = renderButton({ variant: 'sm' });
    expect(btn.className).toContain('sm');
  });

  it('does NOT apply the "sm" class on a default (primary) button', () => {
    const btn = renderButton({ variant: 'primary' });
    // class string should not have a standalone 'sm' segment
    const classes = btn.className.split(/\s+/);
    expect(classes).not.toContain('sm');
  });
});

// ---------------------------------------------------------------------------
// 4. Disabled state
// ---------------------------------------------------------------------------

describe('Button — disabled state', () => {
  it('has the native "disabled" attribute when disabled prop is true', () => {
    const btn = renderButton({ disabled: true });
    expect(btn).toBeDisabled();
  });

  it('has aria-disabled="true" when disabled prop is true', () => {
    const btn = renderButton({ disabled: true });
    expect(btn.getAttribute('aria-disabled')).toBe('true');
  });

  it('applies the "disabled" CSS class when disabled prop is true', () => {
    const btn = renderButton({ disabled: true });
    expect(btn.className).toContain('disabled');
  });

  it('does NOT apply "disabled" class when disabled prop is false', () => {
    const btn = renderButton({ disabled: false });
    const classes = btn.className.split(/\s+/);
    expect(classes).not.toContain('disabled');
  });

  it('does NOT call onClick when the button is disabled and clicked', () => {
    const onClick = vi.fn();
    const btn = renderButton({ disabled: true, onClick });
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('calls onClick when the button is enabled and clicked', () => {
    const onClick = vi.fn();
    const btn = renderButton({ disabled: false, onClick });
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// 5. Children rendering
// ---------------------------------------------------------------------------

describe('Button — children', () => {
  it('renders text children inside the button', () => {
    const { getByText } = render(<Button>Save Changes</Button>);
    expect(getByText('Save Changes')).toBeTruthy();
  });

  it('renders element children inside the button', () => {
    const { getByTestId } = render(
      <Button>
        <span data-testid="icon">★</span>
      </Button>,
    );
    expect(getByTestId('icon')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 6. type prop
// ---------------------------------------------------------------------------

describe('Button — type attribute', () => {
  it('defaults to type="button"', () => {
    const btn = renderButton();
    expect(btn.getAttribute('type')).toBe('button');
  });

  it('applies type="submit" when specified', () => {
    const btn = renderButton({ type: 'submit' });
    expect(btn.getAttribute('type')).toBe('submit');
  });

  it('applies type="reset" when specified', () => {
    const btn = renderButton({ type: 'reset' });
    expect(btn.getAttribute('type')).toBe('reset');
  });
});

// ---------------------------------------------------------------------------
// 7. Additional className merging
// ---------------------------------------------------------------------------

describe('Button — className prop', () => {
  it('merges the additional className with the module classes', () => {
    const btn = renderButton({ className: 'custom-class' });
    expect(btn.className).toContain('custom-class');
    expect(btn.className).toContain('btn');
  });
});

// ---------------------------------------------------------------------------
// 8. aria-label
// ---------------------------------------------------------------------------

describe('Button — aria-label', () => {
  it('applies aria-label when provided', () => {
    const btn = renderButton({ 'aria-label': 'Close dialog' });
    expect(btn.getAttribute('aria-label')).toBe('Close dialog');
  });
});
