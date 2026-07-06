import React from 'react';
import styles from './PageHeader.module.css';

/**
 * Props for the PageHeader component.
 */
export interface PageHeaderProps {
  /** Main page title — rendered at 20px / font-weight 700 */
  title: string;
  /** Optional subtitle rendered below the title at 13px / neutral-600 */
  subtitle?: string;
  /** Optional right-aligned slot for action buttons or controls */
  actions?: React.ReactNode;
  /** Additional CSS class names applied to the root element */
  className?: string;
}

/**
 * PageHeader component.
 *
 * A standardised page-level header placed at the top of every page content
 * area. It displays the page title, an optional subtitle, and an optional
 * right-aligned actions slot for buttons or other controls.
 *
 * Uses design-system tokens for all spacing, colour, radius, and shadow
 * values. No hardcoded values are used.
 *
 * @example
 * // Basic usage with title only
 * <PageHeader title="Users" />
 *
 * @example
 * // With subtitle and action buttons
 * <PageHeader
 *   title="Audit Logs"
 *   subtitle="Review all system activity"
 *   actions={<Button variant="primary">Export</Button>}
 * />
 */
export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps): React.ReactElement {
  return (
    <div className={[styles.pageHeader, className].filter(Boolean).join(' ')}>
      {/* Left side: title and optional subtitle */}
      <div className={styles.titleGroup}>
        <h1 className={styles.title}>{title}</h1>
        {subtitle !== undefined && (
          <p className={styles.subtitle}>{subtitle}</p>
        )}
      </div>

      {/* Right side: optional actions slot */}
      {actions !== undefined && (
        <div className={styles.actions}>{actions}</div>
      )}
    </div>
  );
}
