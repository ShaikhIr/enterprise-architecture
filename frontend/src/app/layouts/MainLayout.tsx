/**
 * Main application layout - Emcure Vertical Sidebar.
 * Matches the Emcure Theme v2.0 design system.
 */

import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Avatar } from 'primereact/avatar';
import { Menu } from 'primereact/menu';
import { Badge } from 'primereact/badge';
import { useRef } from 'react';
import { useAppDispatch, useAppSelector } from '@app/store';
import { logout } from '@features/authentication/store/authSlice';
import { useMenuPermissions } from '@core/rbac/usePermissions';

interface NavItem {
  label: string;
  icon: string;
  path: string;
  visible?: boolean;
  section?: string;
  menuKey?: string;
}

export const MainLayout = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAppSelector((state) => state.auth);
  const userMenu = useRef<Menu>(null);
  const { menuKeys, isLoaded: rbacLoaded } = useMenuPermissions();

  const navItems: NavItem[] = [
    { label: 'Dashboard', icon: 'pi pi-th-large', path: '/dashboard', section: 'Main', menuKey: 'dashboard' },
    { label: 'Orders', icon: 'pi pi-list', path: '/orders', section: 'Main' },
    { label: 'Reports', icon: 'pi pi-chart-bar', path: '/reports', section: 'Main', menuKey: 'reports' },
    { label: 'Inventory', icon: 'pi pi-box', path: '/inventory', section: 'Main' },
    { label: 'Users', icon: 'pi pi-users', path: '/users', section: 'Management', menuKey: 'users' },
    { label: 'Roles & Permissions', icon: 'pi pi-shield', path: '/roles', section: 'Management', menuKey: 'roles' },
    { label: 'Audit Logs', icon: 'pi pi-history', path: '/audit-logs', section: 'Management', menuKey: 'audit_logs' },
    { label: 'Settings', icon: 'pi pi-cog', path: '/settings', section: 'Management', menuKey: 'settings' },
    { label: 'Employee AD', icon: 'pi pi-id-card', path: '/services/employee-ad', section: 'Services', menuKey: 'services' },
  ];

  // Filter items based on RBAC menu permissions
  // ADMIN role gets full access as a fallback (in case role_assignments not seeded)
  const isAdmin = user?.role === 'ADMIN';

  const visibleItems = navItems.filter((item) => {
    // If no menuKey specified, always show
    if (!item.menuKey) return item.visible !== false;
    // Admin always sees everything
    if (isAdmin) return true;
    // If RBAC not loaded yet, hide gated items to avoid flash
    if (!rbacLoaded) return false;
    // Show if user has the menu permission
    return menuKeys.includes(item.menuKey);
  });

  const userMenuItems = [
    {
      label: `${user?.username} (${user?.role})`,
      icon: 'pi pi-user',
      disabled: true,
    },
    { separator: true },
    {
      label: 'Profile',
      icon: 'pi pi-id-card',
      command: () => navigate('/profile'),
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

  // Group items by section
  const sections = visibleItems.reduce<Record<string, NavItem[]>>((acc, item) => {
    const section = item.section || 'Other';
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  return (
    <div className="min-h-screen flex" style={{ background: '#F8F9FA' }}>
      {/* ─── Vertical Sidebar ─── */}
      <aside
        className="em-sidebar flex-shrink-0 hidden md:flex flex-column"
        style={{ width: '260px', minHeight: '100vh' }}
        aria-label="Sidebar navigation"
      >
        {/* Logo */}
        <div
          className="flex align-items-center gap-2 px-4"
          style={{ height: '60px', borderBottom: '1px solid var(--color-surface-border)' }}
        >
          <span
            className="font-bold text-xl"
            style={{ color: 'var(--color-primary)' }}
          >
            EMCURE
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 px-3">
          {Object.entries(sections).map(([section, items]) => (
            <div key={section} className="mb-3">
              <div
                className="text-xs font-semibold uppercase mb-2 px-3"
                style={{ color: 'var(--color-text-muted)', letterSpacing: '0.05em' }}
              >
                {section}
              </div>
              {items.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <button
                    key={item.path}
                    onClick={() => navigate(item.path)}
                    className={`w-full flex align-items-center gap-3 px-3 py-2 mb-1 border-none cursor-pointer transition-colors transition-duration-200 ${
                      isActive ? 'sidebar-active' : ''
                    }`}
                    style={{
                      background: isActive ? 'var(--color-primary-50)' : 'transparent',
                      borderRadius: 'var(--radius-md)',
                      borderLeft: isActive ? '3px solid var(--color-primary)' : '3px solid transparent',
                      color: isActive ? 'var(--color-primary)' : 'var(--color-text-primary)',
                      fontWeight: isActive ? 600 : 400,
                      fontSize: '14px',
                    }}
                    aria-label={item.label}
                    aria-current={isActive ? 'page' : undefined}
                  >
                    <i
                      className={item.icon}
                      style={{
                        fontSize: '1rem',
                        color: isActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                      }}
                    />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/* ─── Main Content Area ─── */}
      <div className="flex-1 flex flex-column" style={{ minWidth: 0, maxWidth: 'calc(100vw - 260px)' }}>
        {/* Top Bar */}
        <header
          className="em-topbar flex align-items-center justify-content-between px-4"
          style={{ height: '60px' }}
          aria-label="Top bar"
        >
          {/* Left: Page breadcrumb or search can go here */}
          <div className="flex align-items-center gap-3">
            <span className="text-lg font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {navItems.find((i) => i.path === location.pathname)?.label || 'Dashboard'}
            </span>
          </div>

          {/* Right: Notifications + User */}
          <div className="flex align-items-center gap-3">
            {/* Notification bell */}
            <Button
              icon="pi pi-bell"
              rounded
              outlined
              severity="secondary"
              aria-label="Notifications"
              className="p-overlay-badge"
            >
              <Badge value="3" severity="danger" />
            </Button>

            {/* User avatar & menu */}
            <Menu model={userMenuItems} popup ref={userMenu} />
            <Button
              rounded
              text
              onClick={(e) => userMenu.current?.toggle(e)}
              aria-label="User menu"
              className="flex align-items-center gap-2"
            >
              <Avatar
                label={user?.username?.charAt(0).toUpperCase() || 'U'}
                shape="circle"
                style={{ background: 'var(--color-primary)', color: '#fff' }}
              />
              <span
                className="hidden lg:inline font-medium"
                style={{ color: 'var(--color-text-primary)', fontSize: '14px' }}
              >
                {user?.username?.substring(0, 2).toUpperCase()}
              </span>
            </Button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
