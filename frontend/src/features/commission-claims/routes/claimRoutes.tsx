/**
 * Commission Claims module route configuration.
 *
 * Routes:
 *   /claims                   → ClaimsListPage  (grid of all claims + New Claim button)
 *   /claims/:claimId/edit     → CreateClaimPage (draft editor — add lines, upload POD)
 *   /claims/:claimId          → ClaimDetailPage (approver view with workflow actions)
 *   /claims/approval-queue    → ApprovalQueuePage
 *   /claims/mis/pending       → MISPendingPage
 *   /claims/mis/history       → MISHistoryPage
 *
 * Requirements: 19.1, 20.1, 21.1
 */

import { Route } from 'react-router-dom';
import { PrivateRoute } from '@app/router/PrivateRoute';
import { ClaimsListPage } from '../pages/ClaimsListPage';
import { CreateClaimPage } from '../pages/CreateClaimPage';
import { ClaimDetailPage } from '../pages/ClaimDetailPage';
import { ApprovalQueuePage } from '../pages/ApprovalQueuePage';
import { MISPendingPage } from '../pages/MISPendingPage';
import { MISHistoryPage } from '../pages/MISHistoryPage';

export const renderClaimRoutes = () => (
  <>
    {/* Static routes first to avoid React Router matching them as /:claimId */}
    <Route
      path="approval-queue"
      element={
        <PrivateRoute menuKey="claims">
          <ApprovalQueuePage />
        </PrivateRoute>
      }
    />
    <Route
      path="mis/pending"
      element={
        <PrivateRoute menuKey="claims_mis">
          <MISPendingPage />
        </PrivateRoute>
      }
    />
    <Route
      path="mis/history"
      element={
        <PrivateRoute menuKey="claims_mis">
          <MISHistoryPage />
        </PrivateRoute>
      }
    />

    {/* Index — claims list grid */}
    <Route
      index
      element={
        <PrivateRoute menuKey="claims">
          <ClaimsListPage />
        </PrivateRoute>
      }
    />

    {/* Draft editor — only reachable after a claim is created */}
    <Route
      path=":claimId/edit"
      element={
        <PrivateRoute menuKey="claims">
          <CreateClaimPage />
        </PrivateRoute>
      }
    />

    {/* Claim detail / approver view */}
    <Route
      path=":claimId"
      element={
        <PrivateRoute menuKey="claims">
          <ClaimDetailPage />
        </PrivateRoute>
      }
    />
  </>
);
