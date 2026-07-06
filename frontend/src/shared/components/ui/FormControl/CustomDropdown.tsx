import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactDOM from 'react-dom';
import styles from './CustomDropdown.module.css';

/**
 * Represents a single selectable option in the CustomDropdown.
 */
export interface DropdownOption {
  /** The value submitted when this option is selected. Accepts string or number. */
  value: string | number;
  /** The human-readable label displayed for this option. */
  label: string;
}

/**
 * Props for the CustomDropdown component.
 */
export interface CustomDropdownProps {
  /** Array of selectable options rendered in the dropdown panel. */
  options: DropdownOption[];
  /** The currently selected value, or `null` when nothing is selected. */
  value: string | number | null;
  /** Callback fired when the user selects an option. Receives the selected value. */
  onChange: (value: string | number) => void;
  /** Placeholder text shown in the trigger when no value is selected. */
  placeholder?: string;
  /** When `true`, the trigger is not interactive and the dropdown will not open. */
  disabled?: boolean;
  /** Additional class names applied to the trigger element. */
  className?: string;
}

/**
 * CustomDropdown
 *
 * A fully styled dropdown component that matches the Emcure Design System
 * `.form-control` aesthetic. Renders the option panel in a React portal
 * (directly into `document.body`) to avoid ancestor `overflow: hidden` clipping.
 *
 * - Trigger adopts `--color-primary` border and squared bottom corners when open.
 * - Panel slides in via the `dropIn` keyframe animation over `--duration-normal`.
 * - Option hover: `--color-primary-50` background, `--color-primary` text.
 * - Option selected: `--color-primary-100` background, `font-weight: 500`.
 * - Closes when the user clicks outside the trigger or panel.
 *
 * @example
 * const options = [
 *   { value: 'a', label: 'Option A' },
 *   { value: 'b', label: 'Option B' },
 * ];
 *
 * <CustomDropdown
 *   options={options}
 *   value={selected}
 *   onChange={setSelected}
 *   placeholder="Choose an option"
 * />
 */
export const CustomDropdown: React.FC<CustomDropdownProps> = ({
  options,
  value,
  onChange,
  placeholder = 'Select…',
  disabled = false,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties>({});
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  /** Recalculate panel position from trigger's bounding rect. */
  const updatePanelPosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPanelStyle({
      position: 'fixed',
      top: rect.bottom,
      left: rect.left,
      width: rect.width,
    });
  }, []);

  /** Open the dropdown. */
  const handleTriggerClick = () => {
    if (disabled) return;
    if (!isOpen) {
      updatePanelPosition();
    }
    setIsOpen((prev) => !prev);
  };

  /** Close on outside mousedown. */
  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current &&
        !triggerRef.current.contains(target) &&
        panelRef.current &&
        !panelRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideMouseDown);
    return () => {
      document.removeEventListener('mousedown', handleOutsideMouseDown);
    };
  }, [isOpen]);

  /** Select an option and close the panel. */
  const handleOptionSelect = (optionValue: string | number) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  /** Resolve the label for the current value. */
  const selectedLabel =
    value !== null
      ? (options.find((o) => o.value === value)?.label ?? placeholder)
      : placeholder;

  const triggerClass = [
    styles.trigger,
    isOpen ? styles.triggerOpen : '',
    disabled ? styles.triggerDisabled : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const panel = isOpen
    ? ReactDOM.createPortal(
        <div
          ref={panelRef}
          className={styles.panel}
          style={panelStyle}
          role="listbox"
          aria-label="Dropdown options"
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            const optionClass = [
              styles.option,
              isSelected ? styles.optionSelected : '',
            ]
              .filter(Boolean)
              .join(' ');

            return (
              <div
                key={option.value}
                role="option"
                aria-selected={isSelected}
                className={optionClass}
                onMouseDown={(e) => {
                  // Use mousedown so it fires before the outside-click handler.
                  e.preventDefault();
                  handleOptionSelect(option.value);
                }}
              >
                {option.label}
              </div>
            );
          })}
        </div>,
        document.body
      )
    : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={triggerClass}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        disabled={disabled}
        onClick={handleTriggerClick}
      >
        <span className={styles.triggerLabel}>{selectedLabel}</span>
        {/* Chevron icon — rotates 180° when the panel is open */}
        <svg
          className={[styles.chevron, isOpen ? styles.chevronOpen : '']
            .filter(Boolean)
            .join(' ')}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          focusable="false"
        >
          <path
            d="M2 4L6 8L10 4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {panel}
    </>
  );
};

export default CustomDropdown;
