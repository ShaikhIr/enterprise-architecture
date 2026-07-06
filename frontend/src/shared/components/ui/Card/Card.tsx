import React from 'react';
import styles from './Card.module.css';

/**
 * Props for the Card root component.
 */
export interface CardProps {
  /** Optional header text — when provided, renders a CardHeader above the body */
  header?: string;
  /** Card body content */
  children: React.ReactNode;
  /** Additional CSS class names applied to the card root */
  className?: string;
}

/**
 * Props for the CardHeader sub-component.
 */
export interface CardHeaderProps {
  /** Header content */
  children: React.ReactNode;
  /** Additional CSS class names applied to the card header */
  className?: string;
}

/**
 * Props for the CardBody sub-component.
 */
export interface CardBodyProps {
  /** Body content */
  children: React.ReactNode;
  /** Additional CSS class names applied to the card body */
  className?: string;
}

/**
 * CardHeader sub-component.
 *
 * Renders a styled header section with a bottom border separator.
 * Can be used standalone for flexible card composition or rendered
 * automatically by the `Card` root when the `header` prop is supplied.
 *
 * @example
 * <CardHeader>My Section</CardHeader>
 */
export function CardHeader({ children, className }: CardHeaderProps): React.ReactElement {
  return (
    <div className={[styles.cardHeader, className].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}

/**
 * CardBody sub-component.
 *
 * Renders a padded body section inside a card.
 * Can be used standalone for flexible card composition or rendered
 * automatically by the `Card` root.
 *
 * @example
 * <CardBody>Content goes here</CardBody>
 */
export function CardBody({ children, className }: CardBodyProps): React.ReactElement {
  return (
    <div className={[styles.cardBody, className].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
}

/**
 * Card component.
 *
 * A reusable content container with optional header and body sections.
 * Provide the `header` prop to render a titled header above the body.
 * For full compositional control use `CardHeader` and `CardBody` directly.
 *
 * @example
 * // Simple card with header
 * <Card header="Patient Details">
 *   <p>Content here</p>
 * </Card>
 *
 * @example
 * // Composed card without the header prop
 * <Card>
 *   <CardHeader>Custom Header</CardHeader>
 *   <CardBody>Content here</CardBody>
 * </Card>
 */
export function Card({ header, children, className }: CardProps): React.ReactElement {
  return (
    <div className={[styles.card, className].filter(Boolean).join(' ')}>
      {header !== undefined && <CardHeader>{header}</CardHeader>}
      <CardBody>{children}</CardBody>
    </div>
  );
}
