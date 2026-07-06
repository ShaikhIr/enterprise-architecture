import React from 'react';
import styles from './StatusBadge.module.css';

/**
 * All supported visual/semantic variants for the StatusBadge component.
 *
 * Flat variants (background + text color):
 *   success | warning | error | info | draft
 *
 * Gradient variants (CSS linear-gradient background):
 *   completed | overdue | waiting | assigned | referred
 */
export type StatusBadgeVariant =
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'draft'
  | 'completed'
  | 'overdue'
  | 'waiting'
  | 'assigned'
  | 'referred';

/**
 * Props for the StatusBadge component.
 */
export interface StatusBadgeProps {
  /** Visual/semantic variant controlling the badge color scheme. */
  variant: StatusBadgeVariant;
  /** Label text displayed inside the badge — rendered uppercase via CSS. */
  label: string;
  /** Optional additional CSS class names to apply to the badge element. */
  className?: string;
}

/**
 * StatusBadge
 *
 * A pill-shaped, colour-coded label used to communicate record or workflow
 * status at a glance. Renders a small dot (`::before`) followed by the
 * uppercased label text.
 *
 * @example
 * ```tsx
 * <StatusBadge variant="success" label="Active" />
 * <StatusBadge variant="overdue" label="Overdue" />
 * ```
 */
const StatusBadge: React.FC<StatusBadgeProps> = ({ variant, label, className }) => {
  const variantClass = styles[variant];

  return (
    <span
      className={[styles.badge, variantClass, className].filter(Boolean).join(' ')}
      aria-label={`Status: ${label}`}
    >
      {label}
    </span>
  );
};

export default StatusBadge;
