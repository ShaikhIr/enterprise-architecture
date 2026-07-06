import React from 'react';
import styles from './FormControl.module.css';

/**
 * Props for the FormControl component.
 *
 * Extends native `InputHTMLAttributes` so all standard HTML attributes
 * (placeholder, value, onChange, disabled, etc.) are supported out of the box.
 * Use the `as` prop to switch the underlying element to `textarea` or `select`.
 */
interface FormControlProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Renders the control as a different HTML element. Defaults to `input`. */
  as?: 'input' | 'textarea' | 'select';
  /** Additional class names to merge onto the root element. */
  className?: string;
  /** Child elements — required when `as="select"` to provide `<option>` nodes. */
  children?: React.ReactNode;
}

/**
 * FormControl
 *
 * A polymorphic form field component that applies the Emcure Design System
 * `.formControl` styles to `input`, `textarea`, or `select` elements.
 *
 * @example
 * // Text input (default)
 * <FormControl placeholder="Enter value" />
 *
 * @example
 * // Textarea
 * <FormControl as="textarea" rows={4} />
 *
 * @example
 * // Select
 * <FormControl as="select">
 *   <option value="">Choose…</option>
 *   <option value="a">Option A</option>
 * </FormControl>
 */
const FormControl = React.forwardRef<
  HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  FormControlProps
>(({ as = 'input', className, children, ...rest }, ref) => {
  const combinedClassName = [styles.formControl, className].filter(Boolean).join(' ');

  if (as === 'textarea') {
    // Cast rest to textarea attributes — the underlying element is a <textarea>.
    const textareaProps = rest as React.TextareaHTMLAttributes<HTMLTextAreaElement>;
    return (
      <textarea
        ref={ref as React.Ref<HTMLTextAreaElement>}
        className={combinedClassName}
        {...textareaProps}
      />
    );
  }

  if (as === 'select') {
    // Cast rest to select attributes — the underlying element is a <select>.
    const selectProps = rest as React.SelectHTMLAttributes<HTMLSelectElement>;
    return (
      <select
        ref={ref as React.Ref<HTMLSelectElement>}
        className={combinedClassName}
        {...selectProps}
      >
        {children}
      </select>
    );
  }

  // Default: render as <input>
  return (
    <input
      ref={ref as React.Ref<HTMLInputElement>}
      className={combinedClassName}
      {...rest}
    />
  );
});

FormControl.displayName = 'FormControl';

export default FormControl;
export type { FormControlProps };
