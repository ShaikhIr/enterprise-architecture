import React from 'react';
import styles from './KpiCard.module.css';

/**
 * Color variant for the KpiCard icon background box.
 *
 * - `red`    — red tint with primary brand color icon
 * - `green`  — green tint with success color icon
 * - `orange` — amber tint with warning color icon
 * - `blue`   — blue tint with info color icon
 * - `violet` — violet tint with purple icon
 * - `slate`  — slate/grey tint with muted icon
 */
export type KpiIconColor = 'red' | 'green' | 'orange' | 'blue' | 'violet' | 'slate';

/**
 * Props for the KpiCard component.
 */
export interface KpiCardProps {
  /** Icon element rendered inside the 46×46px icon box. */
  icon: React.ReactNode;
  /** Color variant for the icon background box. Defaults to `'red'`. */
  iconColor?: KpiIconColor;
  /** Primary numeric or text metric value rendered prominently. */
  value: string | number;
  /** Descriptive label rendered beneath the value. */
  label: string;
  /**
   * Optional trend delta value.
   * - Positive (`> 0`) → green chip with "+" prefix
   * - Negative (`< 0`) → red chip
   * - Zero (`=== 0`)   → neutral grey chip
   * - Omitted          → no chip rendered
   */
  delta?: number;
  /** Optional additional CSS class names applied to the root element. */
  className?: string;
}

/** Map of KpiIconColor variant names to their corresponding CSS module classes. */
const iconColorClassMap: Record<KpiIconColor, string> = {
  red: styles.iconRed,
  green: styles.iconGreen,
  orange: styles.iconOrange,
  blue: styles.iconBlue,
  violet: styles.iconViolet,
  slate: styles.iconSlate,
};

/**
 * KpiCard
 *
 * A metric display card showing an icon, a numeric/text value, a descriptive
 * label, and an optional trend delta chip. Used in dashboard KPI grids.
 *
 * The card lifts on hover with a primary-border accent and an elevated shadow.
 * The icon box supports six color variants aligned to the design system palette.
 * The delta chip color is determined by the sign of the `delta` prop.
 *
 * @example
 * ```tsx
 * <KpiCard
 *   icon={<i className="pi pi-users" />}
 *   iconColor="blue"
 *   value={1284}
 *   label="Total Users"
 *   delta={12}
 * />
 * ```
 */
const KpiCard: React.FC<KpiCardProps> = ({
  icon,
  iconColor = 'red',
  value,
  label,
  delta,
  className,
}) => {
  const iconClass = iconColorClassMap[iconColor];

  /** Resolve the delta chip class and display text. */
  const renderDelta = (): React.ReactNode => {
    if (delta === undefined) {
      return null;
    }

    let chipClass: string;
    let displayText: string;

    if (delta > 0) {
      chipClass = styles.deltaPositive;
      displayText = `+${delta}`;
    } else if (delta < 0) {
      chipClass = styles.deltaNegative;
      displayText = String(delta);
    } else {
      chipClass = styles.deltaNeutral;
      displayText = '0';
    }

    return (
      <span className={[styles.delta, chipClass].join(' ')}>
        {displayText}
      </span>
    );
  };

  return (
    <div className={[styles.kpiCard, className].filter(Boolean).join(' ')}>
      <div className={[styles.iconBox, iconClass].join(' ')}>
        {icon}
      </div>
      <div className={styles.kpiMeta}>
        <span className={styles.value}>{value}</span>
        <span className={styles.label}>{label}</span>
        {renderDelta()}
      </div>
    </div>
  );
};

export default KpiCard;
