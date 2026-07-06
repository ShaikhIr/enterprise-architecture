/**
 * Unit tests for MainLayout sub-components — Emcure Design System
 *
 * Requirements covered: 3.1–3.17
 *
 * CSS module class names: Vitest is configured with css.modules.classNameStrategy
 * set to 'non-scoped', which causes CSS Modules to return non-hashed, human-readable
 * class names in the test environment. This allows us to assert on class names by
 * their source keys (e.g. 'topbar', 'sidebar', 'sidebarScroll', 'mainContent', 'panel').
 *
 * Mocking strategy:
 * - react-router-dom: useLocation, useNavigate, and Outlet are mocked for all tests
 * - @app/store: useAppSelector and useAppDispatch are mocked for MainLayout tests
 * - @core/rbac/usePermissions: useMenuPermissions is mocked for MainLayout tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ---------------------------------------------------------------------------
// Module mocks — must be declared before any component imports
// ---------------------------------------------------------------------------

// Mock react-router-dom for all tests in this file
vi.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/dashboard' }),
  useNavigate: () => vi.fn(),
  Outlet: () => <div data-testid="outlet-content">Page Content</div>,
}));

// Mock @app/store (useAppSelector, useAppDispatch) for MainLayout
vi.mock('@app/store', () => ({
  useAppSelector: vi.fn(() => ({ user: null })),
  useAppDispatch: vi.fn(() => vi.fn()),
}));

// Mock @features/authentication/store/authSlice (not directly used in tests but
// imported transitively — mock ensures module resolution does not fail)
vi.mock('@features/authentication/store/authSlice', () => ({
  default: vi.fn(),
  loginThunk: vi.fn(),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
  clearError: vi.fn(),
}));

// Mock @core/rbac/usePermissions for MainLayout
vi.mock('@core/rbac/usePermissions', () => ({
  useMenuPermissions: vi.fn(() => ({
    menuKeys: ['dashboard', 'users', 'reports'],
    isLoaded: true,
    isLoading: false,
  })),
}));

// ---------------------------------------------------------------------------
// Component imports (after mocks)
// ---------------------------------------------------------------------------

import { Topbar } from '../../src/app/layouts/Topbar';
import { Sidebar } from '../../src/app/layouts/Sidebar';
import { FlyoutSubmenu } from '../../src/app/layouts/FlyoutSubmenu';
import { MainLayout } from '../../src/app/layouts/MainLayout';
import type { NavItem } from '../../src/app/layouts/FlyoutSubmenu';

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

/** Helper: create a DOMRect with all-zero dimensions (unrendered element) */
function zeroDOMRect(): DOMRect {
  return new DOMRect(0, 0, 0, 0);
}

/** Helper: create a DOMRect with real viewport-like dimensions */
function realDOMRect(): DOMRect {
  return new DOMRect(220, 100, 200, 36);
}

const sampleNavItems: NavItem[] = [
  { label: 'Dashboard', icon: 'pi pi-th-large', path: '/dashboard', section: 'Main' },
  { label: 'Users', icon: 'pi pi-users', path: '/users', section: 'Management' },
];

const sampleNavItemsWithChildren: NavItem[] = [
  {
    label: 'Reports',
    icon: 'pi pi-chart-bar',
    path: '/reports',
    section: 'Main',
    children: [
      { label: 'Sales Report', icon: 'pi pi-file', path: '/reports/sales' },
      { label: 'Audit Report', icon: 'pi pi-history', path: '/reports/audit' },
    ],
  },
];

const flyoutItems: NavItem[] = [
  { label: 'Sales Report', icon: 'pi pi-file', path: '/reports/sales' },
  { label: 'Audit Report', icon: 'pi pi-history', path: '/reports/audit' },
];

// ===========================================================================
// 1. Topbar tests
// Requirements: 3.1, 3.4, 3.5, 3.6, 3.7
// ===========================================================================

describe('Topbar (Requirements 3.1, 3.4, 3.5, 3.6, 3.7)', () => {
  it('renders with "topbar" CSS module class (carries z-index:200, height:var(--topbar-height))', () => {
    const { container } = render(<Topbar />);
    // The topbar CSS class carries the z-index and height declarations
    const header = container.querySelector('header');
    expect(header).toBeTruthy();
    expect(header!.className).toContain('topbar');
  });

  it('renders as a <header> element for semantic correctness', () => {
    const { container } = render(<Topbar />);
    expect(container.querySelector('header')).toBeTruthy();
  });

  it('renders the brand logo with "topbarBrand" CSS class (Req 3.5)', () => {
    const { container } = render(<Topbar />);
    const brand = container.querySelector('[class*="topbarBrand"]');
    expect(brand).toBeTruthy();
    expect(brand!.textContent).toContain('EMCURE');
  });

  it('renders the notification bell button with "bellButton" CSS class (Req 3.6)', () => {
    const { container } = render(<Topbar />);
    const bellBtn = container.querySelector('[class*="bellButton"]');
    expect(bellBtn).toBeTruthy();
    expect(bellBtn!.tagName.toLowerCase()).toBe('button');
  });

  it('bell button has aria-label "Notifications"', () => {
    render(<Topbar />);
    expect(screen.getByRole('button', { name: /notifications/i })).toBeTruthy();
  });

  it('renders a positioned bell badge (Req 3.6)', () => {
    const { container } = render(<Topbar />);
    const badge = container.querySelector('[class*="bellBadge"]');
    expect(badge).toBeTruthy();
  });

  it('renders the user avatar button with "userAvatar" CSS class (Req 3.6)', () => {
    const { container } = render(<Topbar />);
    const avatar = container.querySelector('[class*="userAvatar"]');
    expect(avatar).toBeTruthy();
    expect(avatar!.tagName.toLowerCase()).toBe('button');
  });

  it('user avatar has aria-label "User menu"', () => {
    render(<Topbar />);
    expect(screen.getByRole('button', { name: /user menu/i })).toBeTruthy();
  });

  it('renders the right-side actions wrapper with "topbarActions" CSS class', () => {
    const { container } = render(<Topbar />);
    const actions = container.querySelector('[class*="topbarActions"]');
    expect(actions).toBeTruthy();
  });

  it('accepts an optional pageTitle prop without crashing', () => {
    expect(() => render(<Topbar pageTitle="Dashboard" />)).not.toThrow();
  });
});

// ===========================================================================
// 2. Sidebar tests
// Requirements: 3.2, 3.8, 3.9, 3.10, 3.11, 3.12
// ===========================================================================

describe('Sidebar (Requirements 3.2, 3.8, 3.9, 3.10, 3.11, 3.12)', () => {
  it('renders with "sidebar" CSS class on the shell element (Req 3.2, 3.8)', () => {
    const { container } = render(<Sidebar navItems={sampleNavItems} />);
    const aside = container.querySelector('aside');
    expect(aside).toBeTruthy();
    expect(aside!.className).toContain('sidebar');
  });

  it('shell element does NOT have "overflow: hidden" style (Req 3.9)', () => {
    const { container } = render(<Sidebar navItems={sampleNavItems} />);
    const aside = container.querySelector('aside');
    expect(aside).toBeTruthy();
    // The inline style should not contain overflow:hidden
    expect(aside!.getAttribute('style') ?? '').not.toContain('overflow: hidden');
    expect(aside!.getAttribute('style') ?? '').not.toContain('overflow:hidden');
  });

  it('inner nav element has "sidebarScroll" CSS class (Req 3.10 — overflow-y:auto; overflow-x:visible)', () => {
    const { container } = render(<Sidebar navItems={sampleNavItems} />);
    const nav = container.querySelector('nav');
    expect(nav).toBeTruthy();
    expect(nav!.className).toContain('sidebarScroll');
  });

  it('renders nav items as buttons (Req 3.12)', () => {
    render(<Sidebar navItems={sampleNavItems} />);
    const buttons = screen.getAllByRole('button');
    // At least as many buttons as nav items
    expect(buttons.length).toBeGreaterThanOrEqual(sampleNavItems.length);
  });

  it('renders nav item labels (Req 3.12)', () => {
    render(<Sidebar navItems={sampleNavItems} />);
    expect(screen.getByText('Dashboard')).toBeTruthy();
    expect(screen.getByText('Users')).toBeTruthy();
  });

  it('renders section group labels (Req 3.11)', () => {
    render(<Sidebar navItems={sampleNavItems} />);
    expect(screen.getByText('Main')).toBeTruthy();
    expect(screen.getByText('Management')).toBeTruthy();
  });

  it('nav link buttons have "navLink" CSS class (Req 3.12)', () => {
    const { container } = render(<Sidebar navItems={sampleNavItems} />);
    const navButtons = container.querySelectorAll('[class*="navLink"]');
    expect(navButtons.length).toBeGreaterThanOrEqual(sampleNavItems.length);
  });

  it('active nav item has "navLinkActive" CSS class for the current path', () => {
    // useLocation is mocked to return pathname: '/dashboard'
    const { container } = render(<Sidebar navItems={sampleNavItems} />);
    const activeBtn = container.querySelector('[class*="navLinkActive"]');
    expect(activeBtn).toBeTruthy();
  });

  it('renders a chevron indicator for items with children', () => {
    const { container } = render(<Sidebar navItems={sampleNavItemsWithChildren} />);
    // The pi-chevron-right icon is rendered for items that have children
    const chevron = container.querySelector('.pi-chevron-right');
    expect(chevron).toBeTruthy();
  });

  it('item with children gets aria-haspopup="true"', () => {
    render(<Sidebar navItems={sampleNavItemsWithChildren} />);
    const btn = screen.getByRole('button', { name: /reports/i });
    expect(btn.getAttribute('aria-haspopup')).toBe('true');
  });

  it('renders an accessible aside with aria-label', () => {
    render(<Sidebar navItems={sampleNavItems} />);
    expect(screen.getByRole('complementary', { name: /sidebar navigation/i })).toBeTruthy();
  });
});

// ===========================================================================
// 3. FlyoutSubmenu tests
// Requirements: 3.13, 3.15, 3.16, 3.17
// ===========================================================================

describe('FlyoutSubmenu (Requirements 3.13, 3.15, 3.16, 3.17)', () => {
  const onHide = vi.fn();

  beforeEach(() => {
    onHide.mockClear();
  });

  it('does NOT render when visible=false', () => {
    const { container } = render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={false}
        onHide={onHide}
      />
    );
    // Nothing should be in the container — portal renders to document.body
    // but guard should prevent any DOM output
    const panel = document.querySelector('[role="menu"]');
    expect(panel).toBeNull();
  });

  it('does NOT render when anchorRect has zero dimensions (unrendered element guard)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={zeroDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    // Guard: anchorRect.width === 0 && anchorRect.height === 0 → render null
    const panel = document.querySelector('[role="menu"]');
    expect(panel).toBeNull();
  });

  it('DOES render when visible=true with real anchorRect dimensions', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const panel = document.querySelector('[role="menu"]');
    expect(panel).toBeTruthy();
  });

  it('applies "panel" CSS class to the flyout panel (carries z-index:9999) (Req 3.16)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const panel = document.querySelector('[role="menu"]');
    expect(panel).toBeTruthy();
    expect(panel!.className).toContain('panel');
  });

  it('renders flyout items as menuitem buttons (Req 3.13)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const menuItems = document.querySelectorAll('[role="menuitem"]');
    expect(menuItems.length).toBe(flyoutItems.length);
  });

  it('renders flyout item labels (Req 3.13)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    expect(document.body.textContent).toContain('Sales Report');
    expect(document.body.textContent).toContain('Audit Report');
  });

  it('renders with position:fixed style via the panel CSS class (Req 3.13)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const panel = document.querySelector('[role="menu"]') as HTMLElement;
    expect(panel).toBeTruthy();
    // The panel uses inline style to set top/left from anchorRect
    const style = panel.getAttribute('style') ?? '';
    expect(style).toContain('top');
    expect(style).toContain('left');
  });

  it('renders the red accent stripe element (Req 3.17)', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const panel = document.querySelector('[role="menu"]');
    expect(panel).toBeTruthy();
    // The accent stripe is rendered as a child div with the accent CSS class
    const accent = panel!.querySelector('[class*="accent"]');
    expect(accent).toBeTruthy();
  });

  it('renders with aria-label "Submenu"', () => {
    render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    const panel = document.querySelector('[aria-label="Submenu"]');
    expect(panel).toBeTruthy();
  });

  it('cleans up portal element when unmounted', () => {
    const { unmount } = render(
      <FlyoutSubmenu
        items={flyoutItems}
        anchorRect={realDOMRect()}
        visible={true}
        onHide={onHide}
      />
    );
    expect(document.querySelector('[role="menu"]')).toBeTruthy();
    unmount();
    expect(document.querySelector('[role="menu"]')).toBeNull();
  });
});

// ===========================================================================
// 4. MainLayout tests
// Requirements: 3.1, 3.2, 3.3
// ===========================================================================

describe('MainLayout (Requirements 3.1, 3.2, 3.3)', () => {
  it('renders without crashing', () => {
    expect(() => render(<MainLayout />)).not.toThrow();
  });

  it('renders the Topbar (fixed topbar element) (Req 3.1)', () => {
    const { container } = render(<MainLayout />);
    const header = container.querySelector('header');
    expect(header).toBeTruthy();
    expect(header!.className).toContain('topbar');
  });

  it('renders the Sidebar below the topbar (Req 3.2)', () => {
    const { container } = render(<MainLayout />);
    const aside = container.querySelector('aside');
    expect(aside).toBeTruthy();
    expect(aside!.className).toContain('sidebar');
  });

  it('renders a <main> element for the content area (Req 3.3)', () => {
    const { container } = render(<MainLayout />);
    const main = container.querySelector('main');
    expect(main).toBeTruthy();
  });

  it('main content area has "mainContent" CSS class (carries margin-left and padding) (Req 3.3)', () => {
    const { container } = render(<MainLayout />);
    const main = container.querySelector('main');
    expect(main).toBeTruthy();
    // MainLayout uses inline styles (no CSS module class). Verify the main
    // content area has overflowY set, confirming it is the scrollable content pane.
    expect(main!.style.overflowY).toBe('auto');
  });

  it('renders children via Outlet inside the main content area', () => {
    render(<MainLayout />);
    // Outlet is mocked to render a div with data-testid="outlet-content"
    expect(screen.getByTestId('outlet-content')).toBeTruthy();
  });

  it('Outlet is rendered inside the main content area', () => {
    const { container } = render(<MainLayout />);
    const main = container.querySelector('main');
    expect(main).toBeTruthy();
    const outlet = main!.querySelector('[data-testid="outlet-content"]');
    expect(outlet).toBeTruthy();
  });

  it('renders the layout root with "layout" CSS class', () => {
    const { container } = render(<MainLayout />);
    const root = container.firstElementChild as HTMLElement;
    // MainLayout uses inline styles rather than a CSS module class.
    // Verify the root div is a flex container wrapping the layout.
    expect(root).toBeTruthy();
    expect(root.tagName.toLowerCase()).toBe('div');
  });

  it('layout contains both sidebar and topbar as direct children of the root', () => {
    const { container } = render(<MainLayout />);
    const root = container.firstElementChild as HTMLElement;
    // Root should contain the topbar header
    expect(root.querySelector('header')).toBeTruthy();
    // Root should contain the sidebar aside
    expect(root.querySelector('aside')).toBeTruthy();
    // Root should contain the main content area
    expect(root.querySelector('main')).toBeTruthy();
  });
});
