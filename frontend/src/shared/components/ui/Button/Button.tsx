import React from 'react';
import styles from './Button.module.css';

/**
 * Visual style variants for the Button component.
 *
 * - `primary`   — Red gradient, primary action (e.g. Submit, Confirm).
 * - `secondary` — White background with neutral border; red on hover.
 * - `ghost`     — Transparent, primary-coloured text; subtle hover background.
 * - `danger`    — Solid red, used for destructive or alert-level actions.
 * - `save`      — Green gradient, used for save/confirm-success actions.
 * - `delete`    — Light red background with red text, used for delete actions.
 * - `sm`        — Size modifier (smaller padding + font-size); compose with a
 *                 colour variant via `className` when a coloured small button
 *                 is needed.
 */
export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'ghost'
  | 'danger'
  | 'save'
  | 'delete'
  | 'sm';

/**
 * Props for the {@link Button} component.
 */
export interface ButtonProps {
  /**
   * Visual style variant. Defaults to `'primary'`.
   * The `sm` variant applies a size modifier rather than a colour scheme.
   */
  variant?: ButtonVariant;

  /** Button label and/or icon content. */
  children: React.ReactNode;

  /**
   * Click handler. Not called when the button is disabled — the component
   * adds `pointer-events: none` via CSS in the disabled state, but the native
   * `disabled` attribute is also set for full browser/AT compatibility.
   */
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;

  /**
   * When `true`, the button is visually dimmed, non-interactive, and
   * announces itself as disabled to assistive technologies.
   */
  disabled?: boolean;

  /** HTML `type` attribute. Defaults to `'button'`. */
  type?: 'button' | 'submit' | 'reset';

  /** Additional CSS class name(s) to merge onto the root element. */
  className?: string;

  /** ARIA label for icon-only buttons where the visible label is absent. */
  'aria-label'?: string;
}

/**
 * Emcure Design System — **Button**
 *
 * A pill-shaped, accessible button supporting seven design variants.
 * All visual values are sourced from `tokens.css` CSS custom properties.
 *
 * @example
 * // Primary action button
 * <Button variant="primary" onClick={handleSave}>Save</Button>
 *
 * @example
 * // Small ghost button
 * <Button variant="ghost" className={styles.sm}>Cancel</Button>
 *
 * @example
 * // Disabled save button
 * <Button variant="save" disabled>Processing…</Button>
 */
const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  children,
  onClick,
  disabled = false,
  type = 'button',
  className,
  'aria-label': ariaLabel,
}) => {
  const classNames = [
    styles.btn,
    styles[variant],
    disabled ? styles.disabled : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type={type}
      className={classNames}
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  );
};

export default Button;
