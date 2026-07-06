/**
 * Topbar component for the Emcure Design System MainLayout.
 *
 * Renders a fixed top navigation bar with:
 * - Brand logo on the left
 * - Notification bell with badge (animated on hover via `bellRing` keyframe)
 * - User avatar showing first initial, with popup menu for Profile/Logout
 *
 * Fixed at `top: 0; left: 0; right: 0; z-index: 200; height: var(--topbar-height)`.
 *
 * @example
 * <Topbar pageTitle="Dashboard" />
 */

import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu } from 'primereact/menu';
import type { MenuItem } from 'primereact/menuitem';
import { useAppDispatch, useAppSelector } from '@app/store';
import { logout } from '@features/authentication/store/authSlice';
import styles from './MainLayout.module.css';

/** Props for the Topbar component */
export interface TopbarProps {
  /** Current page title — reserved for future breadcrumb/title display */
  pageTitle?: string;
  /** Number of unread notifications — defaults to 0 */
  notificationCount?: number;
}

/**
 * Fixed topbar rendered at the top of every authenticated page.
 * Requirements: 3.1, 3.4, 3.5, 3.6, 3.7
 */
export const Topbar = ({ pageTitle: _pageTitle, notificationCount = 0 }: TopbarProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const menuRef = useRef<Menu>(null);

  const user = useAppSelector((state) => state.auth.user);
  const firstInitial = user?.username ? user.username[0].toUpperCase() : 'U';

  const userMenuItems: MenuItem[] = [
    {
      label: 'Profile',
      icon: 'pi pi-user',
      command: () => navigate('/profile'),
    },
    {
      separator: true,
    },
    {
      label: 'Logout',
      icon: 'pi pi-sign-out',
      command: () => {
        dispatch(logout());
        navigate('/login');
      },
    },
  ];

  return (
    <header className={styles.topbar} aria-label="Top navigation bar">
      {/* ── Brand Logo (left) ── */}
      <div className={styles.topbarBrand}>
        EMCURE
      </div>

      {/* ── Right-side controls ── */}
      <div className={styles.topbarActions}>
        {/* Notification Bell */}
        <div className={styles.bellWrapper}>
          <button
            className={styles.bellButton}
            aria-label="Notifications"
            type="button"
          >
            <i className={`pi pi-bell ${styles.bellIcon}`} aria-hidden="true" />
          </button>
        {/* Positioned badge — hidden when no notifications */}
          <span
            className={styles.bellBadge}
            aria-label={notificationCount > 0 ? `${notificationCount} notification${notificationCount !== 1 ? 's' : ''}` : undefined}
            aria-hidden={notificationCount === 0}
            style={notificationCount === 0 ? { display: 'none' } : undefined}
          >
            {notificationCount > 0 ? notificationCount : null}
          </span>
        </div>

        {/* User Avatar with popup menu */}
        <Menu model={userMenuItems} popup ref={menuRef} id="user-menu" />
        <button
          className={styles.userAvatar}
          aria-label="User menu"
          aria-haspopup="true"
          aria-controls="user-menu"
          type="button"
          onClick={(e) => menuRef.current?.toggle(e)}
        >
          {firstInitial}
        </button>
      </div>
    </header>
  );
};
