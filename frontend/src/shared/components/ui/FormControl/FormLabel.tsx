import React from 'react';
import styles from './FormControl.module.css';

/**
 * Props for the FormLabel component.
 */
export interface FormLabelProps {
  /** The `id` of the form control this label is associated with. */
  htmlFor?: string;
  /** Label text or any renderable content. */
  children: React.ReactNode;
  /** Optional additional class names. */
  className?: string;
}

/**
 * FormLabel renders an accessible `<label>` element styled to the Emcure Design System.
 *
 * Usage:
 * ```tsx
 * <FormLabel htmlFor="email">Email address</FormLabel>
 * <FormControl id="email" type="email" />
 * ```
 */
export const FormLabel: React.FC<FormLabelProps> = ({
  htmlFor,
  children,
  className,
}) => {
  const classes = [styles.label, className].filter(Boolean).join(' ');

  return (
    <label htmlFor={htmlFor} className={classes}>
      {children}
    </label>
  );
};
