/**
 * Main application layout — Sakai-style with Emcure branding.
 * Collapsible fixed sidebar, sticky topbar, independently-scrollable page content.
 *
 * Fix list applied here:
 * #1 – Removed Orders / Reports / Inventory / Settings nav items
 * #2 – Sidebar is position:fixed; page content has its own overflow-y:auto scroll
 * #3 – Profile popup is wider with a proper username header item
 * #4 – Pagination rows-per-page dropdown icons aligned via inline style override
 */

import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Avatar } from 'primereact/avatar';
import { Menu } from 'primereact/menu';
import { Badge } from 'primereact/badge';
import { Tooltip } from 'primereact/tooltip';
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

const TOPBAR_HEIGHT = 48;
const SIDEBAR_WIDTH_EXPANDED = 220;
const SIDEBAR_WIDTH_COLLAPSED = 60;

export const MainLayout = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAppSelector((state) => state.auth);
  const userMenu = useRef<Menu>(null);
  const { menuKeys, isLoaded: rbacLoaded } = useMenuPermissions();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // ── Nav items (#1: Orders / Reports / Inventory / Settings removed) ──────────
  const navItems: NavItem[] = [
    { label: 'Dashboard',          icon: 'pi pi-th-large',     path: '/dashboard',               section: 'Main',       menuKey: 'dashboard' },
    { label: 'Commission Claims',  icon: 'pi pi-wallet',       path: '/claims',                  section: 'Main',       menuKey: 'dashboard' },
    { label: 'Users',              icon: 'pi pi-users',        path: '/users',                   section: 'Management', menuKey: 'users' },
    { label: 'Roles & Permissions',icon: 'pi pi-shield',       path: '/roles',                   section: 'Management', menuKey: 'roles' },
    { label: 'Audit Logs',         icon: 'pi pi-history',      path: '/audit-logs',              section: 'Management', menuKey: 'audit_logs' },
    { label: 'Workflows',          icon: 'pi pi-sitemap',      path: '/workflows',               section: 'Workflow',   menuKey: 'workflows' },
    { label: 'Approval Matrix',    icon: 'pi pi-check-square', path: '/approval-matrix',         section: 'Workflow',   menuKey: 'workflows' },
    { label: 'Employee AD',        icon: 'pi pi-id-card',      path: '/services/employee-ad',    section: 'Services',   menuKey: 'services' },
    { label: 'Entities',           icon: 'pi pi-building',     path: '/masters/entities',        section: 'Masters',    menuKey: 'entities' },
    { label: 'Vendors',            icon: 'pi pi-briefcase',    path: '/masters/vendors',         section: 'Masters',    menuKey: 'vendors' },
    { label: 'Customers',          icon: 'pi pi-users',        path: '/masters/customers',       section: 'Masters',    menuKey: 'customers' },
    { label: 'Products',           icon: 'pi pi-box',          path: '/masters/products',        section: 'Masters',    menuKey: 'products' },
    { label: 'Agreements',         icon: 'pi pi-file',         path: '/masters/agreements',      section: 'Masters',    menuKey: 'agreements' },
    { label: 'Mappings',           icon: 'pi pi-link',         path: '/masters/mappings',        section: 'Masters',    menuKey: 'mappings' },
    { label: 'Invoices',           icon: 'pi pi-receipt',      path: '/masters/invoices',        section: 'Masters',    menuKey: 'invoices' },
  ];

  const visibleItems = navItems.filter((item) => {
    if (!item.menuKey) return item.visible !== false;
    if (!rbacLoaded) return false;
    return menuKeys.includes(item.menuKey);
  });

  // ── Profile popup items (#3: wider popup, readable username) ─────────────────
  const userMenuItems = [
    {
      // Full username shown as a non-clickable header with an icon
      template: () => (
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--color-surface-border)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <Avatar
            label={user?.username?.charAt(0).toUpperCase() || 'U'}
            shape="circle"
            style={{
              background: 'var(--color-primary)',
              color: '#fff',
              width: '2rem',
              height: '2rem',
              fontSize: '0.85rem',
              flexShrink: 0,
            }}
          />
          <div style={{ overflow: 'hidden' }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: '13px',
                color: 'var(--color-text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '160px',
              }}
            >
              {user?.username || 'User'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
              {(user as any)?.email || ''}
            </div>
          </div>
        </div>
      ),
    },
    {
      label: 'Profile',
      icon: 'pi pi-id-card',
      command: () => navigate('/profile'),
    },
    { separator: true },
    {
      label: 'Logout',
      icon: 'pi pi-sign-out',
      command: () => {
        dispatch(logout());
        navigate('/login');
      },
    },
  ];

  const sections = visibleItems.reduce<Record<string, NavItem[]>>((acc, item) => {
    const section = item.section || 'Other';
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  const currentPage = navItems.find((i) => i.path === location.pathname)?.label || '';

  const sidebarWidth = sidebarCollapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED;

  return (
    <>
      <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--color-surface-ground)' }}>

        {/* ─── Sidebar: position:fixed so it never scrolls with the page (#2) ───── */}
        <aside
          className="em-sidebar"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            bottom: 0,
            width: `${sidebarWidth}px`,
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            transition: 'width 200ms ease',
            background: 'var(--color-surface)',
            borderRight: '1px solid var(--color-surface-border)',
          }}
          aria-label="Sidebar navigation"
        >
          {/* Logo / collapse toggle */}
          <div
            style={{
              height: `${TOPBAR_HEIGHT}px`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: sidebarCollapsed ? 'center' : 'space-between',
              padding: '0 12px',
              borderBottom: '1px solid var(--color-surface-border)',
              flexShrink: 0,
            }}
          >
            {!sidebarCollapsed && (
              <span style={{ fontWeight: 800, fontSize: '16px', color: 'var(--color-primary)', letterSpacing: '-0.01em' }}>
                EMCURE
              </span>
            )}
            <Button
              icon={sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'}
              rounded
              text
              severity="secondary"
              size="small"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              aria-label="Toggle sidebar"
              style={{ minWidth: '1.75rem', height: '1.75rem' }}
            />
          </div>

          {/* Nav list — independently scrollable */}
          <nav
            style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px 4px' }}
          >
            {Object.entries(sections).map(([section, items]) => (
              <div key={section} style={{ marginBottom: '8px' }}>
                {!sidebarCollapsed && (
                  <div
                    style={{
                      fontSize: '0.6rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      color: 'var(--color-text-muted)',
                      padding: '4px 8px 2px',
                    }}
                  >
                    {section}
                  </div>
                )}
                {items.map((item) => {
                  const isActive = location.pathname === item.path;
                  return (
                    <button
                      key={item.path}
                      onClick={() => navigate(item.path)}
                      style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                        padding: sidebarCollapsed ? '8px 4px' : '7px 8px',
                        marginBottom: '2px',
                        border: 'none',
                        borderLeft: !sidebarCollapsed
                          ? isActive
                            ? '3px solid var(--color-primary)'
                            : '3px solid transparent'
                          : undefined,
                        borderRadius: 'var(--radius-md)',
                        background: isActive ? 'var(--color-primary-50)' : 'transparent',
                        color: isActive ? 'var(--color-primary)' : 'var(--color-text-primary)',
                        fontWeight: isActive ? 600 : 400,
                        fontSize: '12px',
                        cursor: 'pointer',
                        transition: 'background 150ms, color 150ms',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                      }}
                      aria-label={item.label}
                      aria-current={isActive ? 'page' : undefined}
                      data-pr-tooltip={sidebarCollapsed ? item.label : undefined}
                      data-pr-position="right"
                      onMouseEnter={(e) => {
                        if (!isActive) {
                          (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-primary-50)';
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-primary)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) {
                          (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-primary)';
                        }
                      }}
                    >
                      <i
                        className={item.icon}
                        style={{
                          fontSize: sidebarCollapsed ? '1.1rem' : '0.85rem',
                          color: isActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                          flexShrink: 0,
                          width: sidebarCollapsed ? 'auto' : '16px',
                          textAlign: 'center',
                        }}
                      />
                      {!sidebarCollapsed && <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
        </aside>

        {sidebarCollapsed && <Tooltip target="[data-pr-tooltip]" />}

        {/* ─── Right pane: topbar (sticky) + scrollable page content (#2) ────── */}
        <div
          style={{
            marginLeft: `${sidebarWidth}px`,
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            transition: 'margin-left 200ms ease',
            minHeight: '100vh',
          }}
        >
          {/* Top bar — sticky at top of the right pane, does NOT affect sidebar */}
          <header
            className="em-topbar"
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 50,
              height: `${TOPBAR_HEIGHT}px`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 16px',
              flexShrink: 0,
            }}
            aria-label="Top bar"
          >
            {/* Breadcrumb */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
              <i className="pi pi-home" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }} />
              {currentPage && (
                <>
                  <span style={{ color: 'var(--color-text-muted)', fontSize: '11px' }}>/</span>
                  <span style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>{currentPage}</span>
                </>
              )}
            </div>

            {/* Right actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {/* Notification bell */}
              <Button
                icon="pi pi-bell"
                rounded
                text
                severity="secondary"
                aria-label="Notifications"
                className="p-overlay-badge"
                style={{ width: '2rem', height: '2rem' }}
              >
                <Badge
                  value="3"
                  severity="danger"
                  style={{ fontSize: '0.6rem', minWidth: '1rem', height: '1rem', lineHeight: '1rem' }}
                />
              </Button>

              {/* Profile popup (#3: min-width 220px, full username readable) */}
              <Menu model={userMenuItems} popup ref={userMenu} id="user-popup-menu" style={{ minWidth: '220px' }} />
              <Button
                rounded
                text
                onClick={(e) => userMenu.current?.toggle(e)}
                aria-label="User menu"
                aria-haspopup="true"
                aria-controls="user-popup-menu"
                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 8px' }}
              >
                <Avatar
                  label={user?.username?.charAt(0).toUpperCase() || 'U'}
                  shape="circle"
                  style={{
                    background: 'var(--color-primary)',
                    color: '#fff',
                    width: '1.75rem',
                    height: '1.75rem',
                    fontSize: '0.75rem',
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    color: 'var(--color-text-primary)',
                    fontSize: '12px',
                    fontWeight: 500,
                    maxWidth: '120px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {user?.username}
                </span>
              </Button>
            </div>
          </header>

          {/* Page content — this is the only thing that scrolls (#2) */}
          <main style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
            <Outlet />
          </main>
        </div>
      </div>
    </>
  );
};
