/**
 * FlyoutSubmenu — viewport-fixed flyout panel that expands from a Sidebar
 * navigation item when that item has child routes.
 *
 * Positioning is calculated via `getBoundingClientRect()` so the panel always
 * aligns with the triggering sidebar item regardless of scroll position.
 * The component renders into `document.body` via a React portal to ensure the
 * fixed z-index is not clipped by any ancestor overflow or stacking context.
 *
 * Requirements: 3.13, 3.15, 3.16, 3.17
 */

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import styles from './FlyoutSubmenu.module.css';

// ─── Interfaces ──────────────────────────────────────────────────────────────

/**
 * A single navigation item that may contain nested child routes.
 */
export interface NavItem {
  /** Display label for the nav link */
  label: string;
  /** PrimeIcons class string (e.g. "pi pi-chart-bar") */
  icon: string;
  /** Route path */
  path: string;
  /** Optional section grouping key */
  section?: string;
  /** Optional RBAC menu permission key */
  menuKey?: string;
  /** Nested child routes — presence triggers a flyout */
  children?: NavItem[];
}

/**
 * Props for the FlyoutSubmenu component.
 */
export interface FlyoutSubmenuProps {
  /** Child nav items to render in the flyout list */
  items: NavItem[];
  /**
   * DOMRect of the anchor sidebar item, obtained via `getBoundingClientRect()`.
   * The flyout is positioned at `top: anchorRect.top` and
   * `left: anchorRect.right + 8px`.
   */
  anchorRect: DOMRect;
  /** When false the component renders nothing */
  visible: boolean;
  /** Called when the flyout should be hidden (hide-delay is the caller's responsibility) */
  onHide: () => void;
}

// ─── Constants ────────────────────────────────────────────────────────────────

/** Horizontal gap between the sidebar right edge and the flyout panel */
const GAP_PX = 8;

/** Minimum distance (px) to keep the panel bottom away from the viewport bottom */
const VIEWPORT_MARGIN_PX = 16;

/** Estimated flyout panel height used for bottom-clamp calculation (px) */
const ESTIMATED_PANEL_HEIGHT_PX = 300;

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * FlyoutSubmenu renders a floating panel of child navigation links to the right
 * of the Sidebar.
 *
 * @example
 * ```tsx
 * <FlyoutSubmenu
 *   items={item.children}
 *   anchorRect={anchorElement.getBoundingClientRect()}
 *   visible={flyoutVisible}
 *   onHide={() => setFlyoutVisible(false)}
 * />
 * ```
 */
export const FlyoutSubmenu = ({
  items,
  anchorRect,
  visible,
  onHide,
}: FlyoutSubmenuProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Guard: do not render if anchorRect has zero dimensions ─────────────────
  // getBoundingClientRect() returns all-zeros for elements not yet in the DOM.
  if (!visible || (anchorRect.width === 0 && anchorRect.height === 0)) {
    return null;
  }

  // ── Compute position ───────────────────────────────────────────────────────
  // Base: align top of flyout with top of the anchor item; place left edge
  // 8 px to the right of the sidebar's right edge.
  let top = anchorRect.top;
  const left = anchorRect.right + GAP_PX;

  // Viewport bottom clamp: if the flyout would overflow the bottom edge, shift
  // it upward so that its bottom stays within the viewport.
  const flyoutBottom = top + ESTIMATED_PANEL_HEIGHT_PX;
  const viewportLimit = window.innerHeight - VIEWPORT_MARGIN_PX;
  if (flyoutBottom > viewportLimit) {
    top = Math.max(0, viewportLimit - ESTIMATED_PANEL_HEIGHT_PX);
  }

  // ── Close on outside click ─────────────────────────────────────────────────
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    if (!visible) return;

    const handlePointerDown = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onHide();
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [visible, onHide]);

  // ── Render via portal ──────────────────────────────────────────────────────
  return createPortal(
    <div
      ref={panelRef}
      className={styles.panel}
      style={{ top, left }}
      role="menu"
      aria-label="Submenu"
      onMouseLeave={onHide}
    >
      {/* Red gradient left-accent stripe (Req 3.17) */}
      <div className={styles.accent} aria-hidden="true" />

      {/* Navigation items */}
      <div className={styles.content}>
        {items.map((item) => {
          const isActive = location.pathname === item.path;

          return (
            <button
              key={item.path}
              role="menuitem"
              className={`${styles.item} ${isActive ? styles.itemActive : ''}`}
              onClick={() => {
                navigate(item.path);
                onHide();
              }}
              aria-current={isActive ? 'page' : undefined}
            >
              <i className={`${item.icon} ${styles.itemIcon}`} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>,
    document.body,
  );
};

export default FlyoutSubmenu;
