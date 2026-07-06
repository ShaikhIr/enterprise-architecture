import React from 'react';
import styles from './Alert.module.css';

/**
 * Visual/semantic variant controlling the Alert colour scheme.
 *
 * - `success` — green tint, used for confirmations and positive outcomes
 * - `warning` — amber tint, used for cautionary messages
 * - `error`   — red tint, used for failure and destructive-action feedback
 * - `info`    — blue tint, used for neutral informational messages
 */
export type AlertVariant = 'success' | 'warning' | 'error' | 'info';

/**
 * Props for the Alert component.
 */
export interface AlertProps {
  /** Alert type controlling the left-border and text colour scheme. */
  variant: AlertVariant;
  /** Optional bold title rendered above the message. */
  title?: string;
  /** Main alert message text. */
  message?: string;
  /** Optional icon element rendered to the left of the content. */
  icon?: React.ReactNode;
  /** Optional additional CSS class names to apply to the root element. */
  className?: string;
}

/**
 * Alert
 *
 * An inline notification component with a left colour-accent border. Supports
 * four semantic variants (`success`, `warning`, `error`, `info`) and optional
 * `icon`, `title`, and `message` slots.
 *
 * All colour values are driven by the variant class — child elements that use
 * `currentColor` or `opacity` automatically inherit the correct tint.
 *
 * @example
 * ```tsx
 * <Alert variant="success" title="Saved" message="Your changes have been saved." />
 * <Alert variant="error" icon={<ErrorIcon />} message="Something went wrong." />
 * ```
 */
const Alert: React.FC<AlertProps> = ({ variant, title, message, icon, className }) => {
  const variantClass = styles[variant];

  return (
    <div
      className={[styles.alert, variantClass, className].filter(Boolean).join(' ')}
      role="alert"
    >
      {icon !== undefined && (
        <span className={styles.alertIcon}>{icon}</span>
      )}
      <div className={styles.alertContent}>
        {title !== undefined && (
          <span className={styles.alertTitle}>{title}</span>
        )}
        {message !== undefined && (
          <span className={styles.alertMessage}>{message}</span>
        )}
      </div>
    </div>
  );
};

export default Alert;
