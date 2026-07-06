/**
 * Sidebar — fixed vertical navigation panel rendered on every authenticated page.
 *
 * Positioning: `top: var(--topbar-height); left: 0; bottom: 0; width: var(--sidenav-width)`
 *
 * Key design decisions:
 * - The shell element (`.sidebar`) must NOT have `overflow: hidden` so that
 *   FlyoutSubmenu panels can visually escape the sidebar boundary (Req 3.9).
 * - An inner scroll wrapper (`.sidebarScroll`) handles `overflow-y: auto` while
 *   keeping `overflow-x: visible` so flyouts are not clipped (Req 3.10).
 * - Items with `children` show a `FlyoutSubmenu` on mouse enter; the flyout is
 *   hidden with a 150 ms delay after mouse leave so the user can move the pointer
 *   to the flyout without it closing prematurely (Req 3.14).
 *
 * Requirements: 3.2, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
 */

import { useRef, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import styles from './MainLayout.module.css';
import { FlyoutSubmenu } from './FlyoutSubmenu';
import type { NavItem } from './FlyoutSubmenu';

// Re-export NavItem so consumers of Sidebar can import it from a single place.
export type { NavItem };

// ─── Interfaces ───────────────────────────────────────────────────────────────

/**
 * Props for the Sidebar component.
 *
 * @example
 * ```tsx
 * <Sidebar navItems={appNavItems} />
 * ```
 */
export interface SidebarProps {
  /** Navigation items to render. Items with a `children` array trigger a flyout. */
  navItems: NavItem[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

/** Delay (ms) before the flyout is hidden after the mouse leaves the nav item. */
const FLYOUT_HIDE_DELAY_MS = 150;

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * Sidebar renders the fixed vertical navigation panel.
 *
 * Navigation items are grouped by their `section` property. Items that have a
 * `children` array render a `FlyoutSubmenu` to the right when hovered.
 */
export const Sidebar = ({ navItems }: SidebarProps) => {
  const location = useLocation();
  const navigate = useNavigate();

  // ── Flyout state ────────────────────────────────────────────────────────────
  /** The nav item whose flyout is currently open, or null if none. */
  const [activeFlyoutKey, setActiveFlyoutKey] = useState<string | null>(null);
  /** Bounding rect of the nav item element that triggered the flyout. */
  const [anchorRect, setAnchorRect] = useState<DOMRect>(new DOMRect());
  /** Ref to the 150 ms hide-delay timer so it can be cancelled on re-enter. */
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Flyout event handlers ────────────────────────────────────────────────────

  /**
   * Show the flyout immediately when the mouse enters a nav item that has children.
   * Cancels any pending hide timer so moving back into the item re-opens the panel.
   */
  const handleNavItemMouseEnter = useCallback(
    (item: NavItem, element: HTMLElement) => {
      if (!item.children?.length) return;

      // Cancel any pending hide timer (Req 3.14).
      if (hideTimerRef.current !== null) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }

      setAnchorRect(element.getBoundingClientRect());
      setActiveFlyoutKey(item.path);
    },
    [],
  );

  /**
   * Start a 150 ms timer to hide the flyout when the mouse leaves a nav item.
   * If the pointer re-enters the item (or the flyout itself) before the timer
   * fires, the timer is cleared by `handleNavItemMouseEnter` or
   * `handleFlyoutMouseEnter` respectively.
   */
  const handleNavItemMouseLeave = useCallback(() => {
    hideTimerRef.current = setTimeout(() => {
      setActiveFlyoutKey(null);
      hideTimerRef.current = null;
    }, FLYOUT_HIDE_DELAY_MS);
  }, []);

  /**
   * Cancel the hide timer when the mouse enters the flyout panel,
   * keeping the flyout open while the user selects a child item.
   */
  const handleFlyoutMouseEnter = useCallback(() => {
    if (hideTimerRef.current !== null) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  /**
   * Start a 150 ms hide timer when the mouse leaves the flyout panel itself.
   */
  const handleFlyoutHide = useCallback(() => {
    hideTimerRef.current = setTimeout(() => {
      setActiveFlyoutKey(null);
      hideTimerRef.current = null;
    }, FLYOUT_HIDE_DELAY_MS);
  }, []);

  // ── Group nav items by section ───────────────────────────────────────────────
  const sections = navItems.reduce<Record<string, NavItem[]>>((acc, item) => {
    const section = item.section ?? 'Other';
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  // ── Determine the active flyout item for flyout positioning ─────────────────
  const activeFlyoutItem = activeFlyoutKey
    ? navItems.find((item) => item.path === activeFlyoutKey) ?? null
    : null;

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <>
      {/*
        Sidebar shell — Req 3.2: fixed positioning below topbar.
        Req 3.8: white bg + neutral-200 right border.
        Req 3.9: NO overflow:hidden here; flyouts must escape this boundary.
        The `.sidebar` CSS class must not include overflow:hidden (verified in MainLayout.module.css).
      */}
      <aside
        className={styles.sidebar}
        aria-label="Sidebar navigation"
      >
        {/*
          Inner scroll wrapper — Req 3.10: overflow-y:auto; overflow-x:visible.
          This scrolls the nav list vertically while leaving the horizontal axis
          open so flyout panels are not clipped.
        */}
        <nav className={styles.sidebarScroll}>
          {Object.entries(sections).map(([section, items]) => (
            <div key={section}>
              {/* Group label — Req 3.11 */}
              <div className={styles.navGroupLabel} aria-hidden="true">
                {section}
              </div>

              {items.map((item) => {
                const isActive = location.pathname === item.path ||
                  (item.children?.some((child) => location.pathname === child.path) ?? false);
                const hasChildren = Boolean(item.children?.length);

                return (
                  <button
                    key={item.path}
                    className={`${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
                    onClick={() => {
                      // If the item has children, navigate to the first child path.
                      // Otherwise navigate directly to item.path.
                      if (hasChildren && item.children?.[0]) {
                        navigate(item.children[0].path);
                      } else {
                        navigate(item.path);
                      }
                    }}
                    onMouseEnter={(e) =>
                      handleNavItemMouseEnter(item, e.currentTarget)
                    }
                    onMouseLeave={handleNavItemMouseLeave}
                    aria-current={isActive ? 'page' : undefined}
                    aria-haspopup={hasChildren ? 'true' : undefined}
                    aria-expanded={hasChildren ? activeFlyoutKey === item.path : undefined}
                    type="button"
                  >
                    {/* Nav item icon */}
                    <i className={item.icon} aria-hidden="true" />
                    {/* Nav item label */}
                    <span>{item.label}</span>
                    {/* Chevron indicator for items with children */}
                    {hasChildren && (
                      <i
                        className="pi pi-chevron-right"
                        style={{ marginLeft: 'auto', fontSize: '10px', opacity: 0.6 }}
                        aria-hidden="true"
                      />
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/*
        FlyoutSubmenu — rendered outside the sidebar shell via React portal
        so it can escape any overflow constraints.
        Req 3.13: positioned via getBoundingClientRect() to the right, 8px gap.
        Req 3.14: the 150ms hide delay is managed by handleFlyoutHide / handleFlyoutMouseEnter.
      */}
      {activeFlyoutItem?.children && (
        <FlyoutSubmenuWrapper
          items={activeFlyoutItem.children}
          anchorRect={anchorRect}
          visible={activeFlyoutKey !== null}
          onHide={handleFlyoutHide}
          onMouseEnter={handleFlyoutMouseEnter}
        />
      )}
    </>
  );
};

// ─── FlyoutSubmenuWrapper ─────────────────────────────────────────────────────

/**
 * Thin wrapper around `FlyoutSubmenu` that attaches the `onMouseEnter` handler
 * needed to cancel the 150 ms hide timer when the user moves the pointer into
 * the flyout panel.
 *
 * FlyoutSubmenu already handles `onMouseLeave` internally by calling `onHide`,
 * so we only need to intercept `onMouseEnter` at the wrapper level.
 */
interface FlyoutSubmenuWrapperProps {
  items: NavItem[];
  anchorRect: DOMRect;
  visible: boolean;
  onHide: () => void;
  onMouseEnter: () => void;
}

const FlyoutSubmenuWrapper = ({
  items,
  anchorRect,
  visible,
  onHide,
  onMouseEnter,
}: FlyoutSubmenuWrapperProps) => {
  // We render a transparent cover div at the flyout panel position to intercept
  // mouse enter — the actual panel is rendered in a portal by FlyoutSubmenu itself.
  // Instead, we wrap the FlyoutSubmenu in a div with pointer-events:none and use
  // the onMouseEnter on FlyoutSubmenu's portal element via the onHide→wrapper pattern.
  //
  // The cleanest approach: FlyoutSubmenu's portal div already has onMouseLeave → onHide.
  // We need to cancel the timer when re-entering. We pass a wrapped onHide that
  // starts the timer, and separately pass onMouseEnter via a portal overlay.
  //
  // Since FlyoutSubmenu renders into document.body via createPortal, we can't
  // directly attach onMouseEnter from outside. Instead, we render a zero-size
  // interceptor at the same coordinates and rely on the FlyoutSubmenu's
  // onMouseLeave → onHide calling our timer-based handler.
  //
  // The simplest correct solution: override onHide inside FlyoutSubmenu to use
  // the timer-based version, and pass a `onMouseEnter` callback as a prop.
  // Since FlyoutSubmenu does not currently accept onMouseEnter, we apply the
  // cancel behaviour at the sidebar item level (which already re-enters the
  // same item cancelling the timer), and for flyout-interior hovering we use
  // a wrapper div rendered in the portal tree.
  //
  // Given the FlyoutSubmenu API, the cleanest approach is to render a wrapper
  // div around FlyoutSubmenu output. We accomplish this by not using the
  // FlyoutSubmenu portal directly but by rendering the FlyoutSubmenu inside
  // a div that has the mouse handlers.
  //
  // However, FlyoutSubmenu already uses createPortal internally. We cannot wrap
  // that portal output. The correct solution is to extend FlyoutSubmenu with an
  // onMouseEnter prop, OR to handle it differently.
  //
  // Since the task says "Apply 150ms hide delay on mouse leave" and FlyoutSubmenu
  // already calls onHide on its own onMouseLeave, our onHide IS the timer starter.
  // When the user moves from the nav item to the flyout:
  //   1. Mouse leaves nav item → handleNavItemMouseLeave starts 150ms timer.
  //   2. Mouse enters flyout panel → FlyoutSubmenu's own onMouseLeave hasn't fired yet.
  //   3. But FlyoutSubmenu doesn't have onMouseEnter to cancel the timer.
  //
  // Solution: add an invisible interceptor div positioned at the same location
  // that cancels the timer on mouse enter, without interfering with the flyout UI.

  return (
    <>
      {/* Invisible mouse-enter interceptor positioned over the flyout area */}
      <FlyoutEnterInterceptor
        anchorRect={anchorRect}
        visible={visible}
        onMouseEnter={onMouseEnter}
      />
      <FlyoutSubmenu
        items={items}
        anchorRect={anchorRect}
        visible={visible}
        onHide={onHide}
      />
    </>
  );
};

// ─── FlyoutEnterInterceptor ───────────────────────────────────────────────────

import { createPortal } from 'react-dom';

/**
 * An invisible fixed-position div rendered in a portal at the flyout panel's
 * approximate location. It cancels the hide timer when the user's pointer
 * enters the flyout area, keeping the panel open.
 *
 * This is necessary because `FlyoutSubmenu` renders into `document.body` via
 * `createPortal` and does not expose an `onMouseEnter` prop.
 */
interface FlyoutEnterInterceptorProps {
  anchorRect: DOMRect;
  visible: boolean;
  onMouseEnter: () => void;
}

const GAP_PX = 8;

const FlyoutEnterInterceptor = ({
  anchorRect,
  visible,
  onMouseEnter,
}: FlyoutEnterInterceptorProps) => {
  if (!visible || (anchorRect.width === 0 && anchorRect.height === 0)) {
    return null;
  }

  const top = anchorRect.top;
  const left = anchorRect.right + GAP_PX;

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top,
        left,
        // Cover a generous area so any pointer movement toward the flyout
        // cancels the timer. The FlyoutSubmenu itself handles the actual UI.
        width: 240,
        height: 320,
        zIndex: 9998, // Just below the flyout (9999) so it doesn't block clicks
        pointerEvents: 'auto',
        // Completely transparent — purely for mouse event capture
        background: 'transparent',
      }}
      onMouseEnter={onMouseEnter}
      aria-hidden="true"
    />,
    document.body,
  );
};

export default Sidebar;
