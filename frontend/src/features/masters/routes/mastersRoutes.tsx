/**
 * Masters module route configuration.
 *
 * Defines routes for all 8 master entities under the `/masters/` prefix.
 * Each route is wrapped with `PrivateRoute` and the corresponding RBAC `menuKey`.
 *
 * Page components are placeholder divs until the actual pages are implemented
 * in later tasks.
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 13.1, 13.6
 */

import { Route } from 'react-router-dom';
import { PrivateRoute } from '@app/router/PrivateRoute';
import { EntityListPage } from '../pages/EntityListPage';
import { VendorListPage } from '../pages/VendorListPage';
import { CustomerListPage } from '../pages/CustomerListPage';
import { ProductCatalogPage } from '../pages/ProductCatalogPage';
import { AgreementListPage } from '../pages/AgreementListPage';
import { MappingListPage } from '../pages/MappingListPage';
import { InvoiceListPage } from '../pages/InvoiceListPage';

// ─── Route configuration ──────────────────────────────────────────────────────

export interface MasterRouteConfig {
  path: string;
  element: React.ReactNode;
  menuKey: string;
}

/**
 * Route definitions for all master entities.
 * Each entry maps a path segment to a page component and its RBAC menuKey.
 */
export const mastersRouteConfig: MasterRouteConfig[] = [
  { path: 'entities',        element: <EntityListPage />,        menuKey: 'entities' },
  { path: 'vendors',         element: <VendorListPage />,       menuKey: 'vendors' },
  { path: 'customers',       element: <CustomerListPage />,     menuKey: 'customers' },
  { path: 'products',        element: <ProductCatalogPage />,   menuKey: 'products' },
  { path: 'agreements',      element: <AgreementListPage />,    menuKey: 'agreements' },
  { path: 'mappings',        element: <MappingListPage />,       menuKey: 'mappings' },
  { path: 'invoices',        element: <InvoiceListPage />,       menuKey: 'invoices' },
];

/**
 * Generates `<Route>` elements for all master entities, each wrapped
 * with `<PrivateRoute>` and the appropriate `menuKey`.
 *
 * Usage in AppRouter.tsx:
 * ```tsx
 * <Route path="masters">
 *   {renderMastersRoutes()}
 * </Route>
 * ```
 */
export const renderMastersRoutes = () =>
  mastersRouteConfig.map(({ path, element, menuKey }) => (
    <Route
      key={path}
      path={path}
      element={
        <PrivateRoute menuKey={menuKey}>
          {element}
        </PrivateRoute>
      }
    />
  ));
