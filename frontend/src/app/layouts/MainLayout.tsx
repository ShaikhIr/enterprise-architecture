/**
 * Main application layout - Emcure Vertical Sidebar.
 * Matches the Emcure Theme v2.0 design system.
 */

import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Avatar } from 'primereact/avatar';
import { Menu } from 'primereact/menu';
import { Badge } from 'primereact/badge';
import { useRef, useState } from 'react';
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
  children?: NavItem[];
}

export const MainLayout = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAppSelector((state) => state.auth);
  const userMenu = useRef<Menu>(null);
  const { menuKeys, isLoaded: rbacLoaded } = useMenuPermissions();

  const [expandedMenus, setExpandedMenus] = useState<Record<string, boolean>>(() => {
    // Auto-expand menus whose children match the current path
    if (window.location.pathname.startsWith('/masters')) {
      return { Masters: true };
    }
    return {};
  });

  const toggleSubmenu = (label: string) => {
    setExpandedMenus((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  const navItems: NavItem[] = [
    { label: 'Dashboard', icon: 'pi pi-th-large', path: '/dashboard', section: 'Main', menuKey: 'dashboard' },
    { label: 'Commission Claims', icon: 'pi pi-wallet', path: '/claims', section: 'Main', menuKey: 'dashboard' },
    { label: 'Orders', icon: 'pi pi-list', path: '/orders', section: 'Main' },
    { label: 'Reports', icon: 'pi pi-chart-bar', path: '/reports', section: 'Main', menuKey: 'reports' },
    { label: 'Inventory', icon: 'pi pi-box', path: '/inventory', section: 'Main' },
    {
      label: 'Masters',
      icon: 'pi pi-database',
      path: '/masters',
      section: 'Main',
      children: [
        { label: 'Region Master', icon: 'pi pi-globe', path: '/masters/regions', section: 'Main' },
        { label: 'Country Master', icon: 'pi pi-flag', path: '/masters/countries', section: 'Main' },
        { label: 'State Master', icon: 'pi pi-map', path: '/masters/states', section: 'Main' },
        { label: 'City Master', icon: 'pi pi-building', path: '/masters/cities', section: 'Main' },
      ],
    },
    { label: 'Users', icon: 'pi pi-users', path: '/users', section: 'Management', menuKey: 'users' },
    { label: 'Roles & Permissions', icon: 'pi pi-shield', path: '/roles', section: 'Management', menuKey: 'roles' },
    { label: 'Audit Logs', icon: 'pi pi-history', path: '/audit-logs', section: 'Management', menuKey: 'audit_logs' },
    { label: 'Workflows', icon: 'pi pi-sitemap', path: '/workflows', section: 'Workflow', menuKey: 'workflows' },
    { label: 'Approval Matrix', icon: 'pi pi-check-square', path: '/approval-matrix', section: 'Workflow', menuKey: 'workflows' },
    { label: 'Settings', icon: 'pi pi-cog', path: '/settings', section: 'Management', menuKey: 'settings' },
    { label: 'Employee AD', icon: 'pi pi-id-card', path: '/services/employee-ad', section: 'Services', menuKey: 'services' },
  ];

  // Filter items based on RBAC menu permissions
  const visibleItems = navItems.filter((item) => {
    // If no menuKey specified, always show
    if (!item.menuKey) return item.visible !== false;
    // If RBAC not loaded yet, hide gated items to avoid flash
    if (!rbacLoaded) return false;
    // Show if user has the menu permission
    return menuKeys.includes(item.menuKey);
  });

  const userMenuItems = [
    {
      label: `${user?.username}`,
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
        style={{ width: '220px', minHeight: '100vh' }}
        aria-label="Sidebar navigation"
      >
        {/* Logo */}
        <div
          className="flex align-items-center gap-2 px-3"
          style={{ height: '48px', borderBottom: '1px solid var(--color-surface-border)' }}
        >
          <span
            className="font-bold text-xl"
            style={{ color: 'var(--color-primary)' }}
          >
            EMCURE
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-2">
          {Object.entries(sections).map(([section, items]) => (
            <div key={section} className="mb-2">
              <div
                className="text-xs font-semibold uppercase mb-1 px-2"
                style={{ color: 'var(--color-text-muted)', letterSpacing: '0.05em', fontSize: '0.65rem' }}
              >
                {section}
              </div>
              {items.map((item) => {
                const isActive = location.pathname === item.path;
                const hasChildren = item.children && item.children.length > 0;
                const isExpanded = expandedMenus[item.label] || false;
                const isChildActive = hasChildren && item.children!.some((c) => location.pathname === c.path);

                return (
                  <div key={item.path}>
                    <button
                      onClick={() => {
                        if (hasChildren) {
                          toggleSubmenu(item.label);
                        } else {
                          navigate(item.path);
                        }
                      }}
                      className={`w-full flex align-items-center gap-2 px-2 py-2 mb-1 border-none cursor-pointer transition-colors transition-duration-200 ${
                        isActive || isChildActive ? 'sidebar-active' : ''
                      }`}
                      style={{
                        background: isActive || isChildActive ? 'var(--color-primary-50)' : 'transparent',
                        borderRadius: 'var(--radius-md)',
                        borderLeft: isActive || isChildActive ? '3px solid var(--color-primary)' : '3px solid transparent',
                        color: isActive || isChildActive ? 'var(--color-primary)' : 'var(--color-text-primary)',
                        fontWeight: isActive || isChildActive ? 600 : 400,
                        fontSize: '12.5px',
                      }}
                      aria-label={item.label}
                      aria-current={isActive ? 'page' : undefined}
                      aria-expanded={hasChildren ? isExpanded : undefined}
                    >
                      <i
                        className={item.icon}
                        style={{
                          fontSize: '1rem',
                          color: isActive || isChildActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                        }}
                      />
                      <span className="flex-1 text-left">{item.label}</span>
                      {hasChildren && (
                        <i
                          className={`pi ${isExpanded ? 'pi-chevron-down' : 'pi-chevron-right'}`}
                          style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}
                        />
                      )}
                    </button>

                    {/* Submenu children */}
                    {hasChildren && isExpanded && (
                      <div className="ml-3" style={{ borderLeft: '1px solid var(--color-surface-border)' }}>
                        {item.children!.map((child) => {
                          const isChildItemActive = location.pathname === child.path;
                          return (
                            <button
                              key={child.path}
                              onClick={() => navigate(child.path)}
                              className={`w-full flex align-items-center gap-2 px-2 py-2 mb-1 border-none cursor-pointer transition-colors transition-duration-200 ${
                                isChildItemActive ? 'sidebar-active' : ''
                              }`}
                              style={{
                                background: isChildItemActive ? 'var(--color-primary-50)' : 'transparent',
                                borderRadius: 'var(--radius-md)',
                                borderLeft: isChildItemActive ? '2px solid var(--color-primary)' : '2px solid transparent',
                                color: isChildItemActive ? 'var(--color-primary)' : 'var(--color-text-primary)',
                                fontWeight: isChildItemActive ? 600 : 400,
                                fontSize: '12px',
                              }}
                              aria-label={child.label}
                              aria-current={isChildItemActive ? 'page' : undefined}
                            >
                              <i
                                className={child.icon}
                                style={{
                                  fontSize: '0.85rem',
                                  color: isChildItemActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                                }}
                              />
                              <span>{child.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/* ─── Main Content Area ─── */}
      <div className="flex-1 flex flex-column" style={{ minWidth: 0, maxWidth: 'calc(100vw - 220px)' }}>
        {/* Top Bar */}
        <header
          className="em-topbar flex align-items-center justify-content-between px-3"
          style={{ height: '48px' }}
          aria-label="Top bar"
        >
          {/* Left: Page breadcrumb or search can go here */}
          <div className="flex align-items-center gap-3">
            <span className="text-lg font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {navItems.find((i) => i.path === location.pathname)?.label
                || navItems.flatMap((i) => i.children || []).find((c) => c.path === location.pathname)?.label
                || 'Dashboard'}
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
        <main className="flex-1 p-3 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
