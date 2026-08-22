/**
 * Application router.
 * Defines all routes with authentication and RBAC guards.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import { MainLayout } from '@app/layouts/MainLayout';

import { LoginPage } from '@features/authentication/pages/LoginPage';
import { MicrosoftCallbackPage } from '@features/authentication/pages/MicrosoftCallbackPage';
import {
  CountriesPage,
  StatesPage,
  CategoriesOfLawPage,
  LegislationsPage,
  RulesPage,
  TaskTypesPage,
} from '@features/masters';
import { AuditLogsPage } from '@features/rbac-admin/pages/AuditLogsPage';
import { RolesPage } from '@features/rbac-admin/pages/RolesPage';
import { EmployeeADServicePage } from '@features/service-menu/pages/EmployeeADServicePage';
import { UserListPage } from '@features/user-management/pages/UserListPage';
import {
  WorkflowDefinitionsPage,
  WorkflowBuilderPage,
  ApprovalMatrixPage,
} from '@features/workflow-admin';

import { NotFoundPage } from '@shared/components/NotFoundPage';

import { AuthBootstrap } from './AuthBootstrap';
import { PrivateRoute } from './PrivateRoute';
import { PublicRoute } from './PublicRoute';

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <AuthBootstrap>
        <Routes>
          {/* Public routes */}
          {/*
          /login is guest-only: an authenticated caller is sent to the dashboard
          rather than shown the form again. The Microsoft callback stays ungated
          because it has to run its code exchange even when a session already
          exists.
        */}
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
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
              element={
                <PrivateRoute menuKey="dashboard">
                  <div className="p-4">
                    <h2>Dashboard</h2>
                    <p>Welcome to Enterprise Architecture</p>
                  </div>
                </PrivateRoute>
              }
            />
            <Route
              path="users"
              element={
                <PrivateRoute menuKey="users">
                  <UserListPage />
                </PrivateRoute>
              }
            />
            <Route
              path="roles"
              element={
                <PrivateRoute menuKey="roles">
                  <RolesPage />
                </PrivateRoute>
              }
            />
            <Route
              path="audit-logs"
              element={
                <PrivateRoute menuKey="audit_logs">
                  <AuditLogsPage />
                </PrivateRoute>
              }
            />
            {/*
            Master data. All six share the `masters` menu key, matching the single
            MENU-scope permission the backend seeds; the per-master API permissions
            still gate the writes.
          */}
            <Route
              path="masters/countries"
              element={
                <PrivateRoute menuKey={['masters', 'masters.countries']}>
                  <CountriesPage />
                </PrivateRoute>
              }
            />
            <Route
              path="masters/states"
              element={
                <PrivateRoute menuKey={['masters', 'masters.states']}>
                  <StatesPage />
                </PrivateRoute>
              }
            />
            <Route
              path="masters/categories-of-law"
              element={
                <PrivateRoute menuKey={['masters', 'masters.categories_of_law']}>
                  <CategoriesOfLawPage />
                </PrivateRoute>
              }
            />
            <Route
              path="masters/legislations"
              element={
                <PrivateRoute menuKey={['masters', 'masters.legislations']}>
                  <LegislationsPage />
                </PrivateRoute>
              }
            />
            <Route
              path="masters/rules"
              element={
                <PrivateRoute menuKey={['masters', 'masters.rules']}>
                  <RulesPage />
                </PrivateRoute>
              }
            />
            <Route
              path="masters/task-types"
              element={
                <PrivateRoute menuKey={['masters', 'masters.task_types']}>
                  <TaskTypesPage />
                </PrivateRoute>
              }
            />

            {/*
            The builder is nested under the list path so the breadcrumb reads as a
            drill-down. The literal "workflows" index route is declared first, so
            it is never shadowed by the :definitionId segment.
          */}
            <Route
              path="workflows"
              element={
                <PrivateRoute menuKey="workflows">
                  <WorkflowDefinitionsPage />
                </PrivateRoute>
              }
            />
            <Route
              path="workflows/:definitionId"
              element={
                <PrivateRoute menuKey="workflows">
                  <WorkflowBuilderPage />
                </PrivateRoute>
              }
            />
            <Route
              path="approval-matrix"
              element={
                <PrivateRoute menuKey="workflows">
                  <ApprovalMatrixPage />
                </PrivateRoute>
              }
            />
            <Route
              path="services/employee-ad"
              element={
                <PrivateRoute menuKey="services">
                  <EmployeeADServicePage />
                </PrivateRoute>
              }
            />
            {/* 404 for any other path while authenticated — stays inside the app shell */}
            <Route path="*" element={<NotFoundPage />} />
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

          {/*
          No top-level catch-all: unknown paths fall through to the protected
          "/" route, which shows the in-app 404 when authenticated or redirects
          to /login (via PrivateRoute) when not. This prevents unknown URLs from
          logging authenticated users out.
        */}
        </Routes>
      </AuthBootstrap>
    </BrowserRouter>
  );
};
