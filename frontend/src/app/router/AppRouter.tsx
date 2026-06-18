/**
 * Application router.
 * Defines all routes with authentication and RBAC guards.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from '@features/authentication/pages/LoginPage';
import { MicrosoftCallbackPage } from '@features/authentication/pages/MicrosoftCallbackPage';
import { UserListPage } from '@features/user-management/pages/UserListPage';
import { EmployeeADServicePage } from '@features/service-menu/pages/EmployeeADServicePage';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';
import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';
import { MainLayout } from '@app/layouts/MainLayout';
import { PrivateRoute } from './PrivateRoute';

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/microsoft/callback" element={<MicrosoftCallbackPage />} />

        {/* Protected routes with layout */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route
            path="dashboard"
            element={<div className="p-4"><h2>Dashboard</h2><p>Welcome to the Enterprise App</p></div>}
          />
          <Route
            path="users"
            element={
              <PrivateRoute requiredRole="ADMIN">
                <UserListPage />
              </PrivateRoute>
            }
          />
          <Route
            path="roles"
            element={
              <PrivateRoute requiredRole="ADMIN">
                <RolesPage />
              </PrivateRoute>
            }
          />
          <Route
            path="audit-logs"
            element={
              <PrivateRoute requiredRole="ADMIN">
                <AuditLogsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="services/employee-ad"
            element={
              <PrivateRoute requiredRole="ADMIN">
                <EmployeeADServicePage />
              </PrivateRoute>
            }
          />
        </Route>

        {/* Unauthorized */}
        <Route
          path="/unauthorized"
          element={
            <div className="flex align-items-center justify-content-center min-h-screen">
              <div className="text-center">
                <h1 className="text-4xl text-red-500">403</h1>
                <p className="text-600">You don't have permission to access this page.</p>
              </div>
            </div>
          }
        />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
