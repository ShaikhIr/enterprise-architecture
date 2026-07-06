import React from 'react';
import styles from './KpiCard.module.css';

/**
 * Props for the KpiGrid component.
 */
export interface KpiGridProps {
  /** KpiCard elements to lay out in the responsive grid. */
  children: React.ReactNode;
  /** Optional additional CSS class names applied to the grid root element. */
  className?: string;
}

/**
 * KpiGrid
 *
 * A responsive CSS grid wrapper for laying out multiple KpiCard components.
 * Uses `repeat(auto-fill, minmax(200px, 1fr))` so cards fill available width
 * and reflow automatically at smaller viewports.
 *
 * @example
 * ```tsx
 * <KpiGrid>
 *   <KpiCard icon={<i className="pi pi-users" />} value={1284} label="Users" />
 *   <KpiCard icon={<i className="pi pi-file" />} value={342}  label="Documents" />
 * </KpiGrid>
 * ```
 */
const KpiGrid: React.FC<KpiGridProps> = ({ children, className }) => {
  return (
    <div className={[styles.kpiGrid, className].filter(Boolean).join(' ')}>
      {children}
    </div>
  );
};

export default KpiGrid;
