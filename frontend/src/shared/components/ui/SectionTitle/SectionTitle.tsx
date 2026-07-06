import React from 'react';
import styles from './SectionTitle.module.css';

/**
 * Props for the SectionTitle component.
 */
export interface SectionTitleProps {
  /** Label text to display as the section heading */
  children: React.ReactNode;
  /** Additional CSS class names to apply to the root element */
  className?: string;
}

/**
 * SectionTitle renders an all-caps section label with a trailing decorative
 * horizontal rule. Use it to visually group related content within a page.
 *
 * @example
 * ```tsx
 * <SectionTitle>General Information</SectionTitle>
 * ```
 */
export const SectionTitle: React.FC<SectionTitleProps> = ({ children, className }) => {
  return (
    <div className={[styles.sectionTitle, className].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
};

export default SectionTitle;
