# Implementation Plan: Commission Claim Management

## Overview

Implement the Commission Claim Management feature following Clean Architecture: domain
entities and pure calculation logic first, then infrastructure repositories and DB models,
then the application service orchestration, then FastAPI endpoints, and finally the React
frontend module. Property-based tests with Hypothesis validate all 11 correctness
properties close to the code they test.

## Tasks

- [x] 1. Domain layer — entities, enums, and pure calculator
  - [x] 1.1 Create `ClaimStatus` enum, `CLAIM_TRANSITIONS` map, and `TERMINAL_STATUSES` frozenset
    - Create `src/domain/entities/commission_claim.py`
    - Define `ClaimStatus(str, Enum)` with values: Draft, Pending, Referred Back, Rejected, Closed
    - Define `CLAIM_TRANSITIONS: dict[tuple[ClaimStatus, str], ClaimStatus]` with all 6 allowed edges
    - Define `TERMINAL_STATUSES: frozenset[ClaimStatus]` = {Closed, Rejected}
    - _Requirements: 11.1, 11.3, 11.4_

  - [x] 1.2 Create `ClaimHeader` and `ClaimLine` dataclasses
    - Add `ClaimHeader` and `ClaimLine` dataclasses to `commission_claim.py`
    - Include all fields from the design (UUID ids, Decimal amounts, date fields, optional fields)
    - _Requirements: 1.1, 1.2, 1.3, 4.1_

  - [x] 1.3 Implement `CommissionCalculator` pure domain service
    - Create `src/domain/services/commission_calculator.py`
    - Define `CommissionInputs` and `CommissionResult` dataclasses
    - Implement `calculate(inputs: CommissionInputs) -> CommissionResult` with all 7 steps:
      1. `net_amount = max(0, bill_amount_excl_gst − amount_deducted − tds_value)`
      2. `commission_payable_base = net_amount + tds_value + amount_deducted`
      3. `delay_days = (payment_clearing_date − due_date).days`
      4. If `delay_days ≤ 0`: `applicable_commission_percent = max_commission_percent`
      5. Else: `bucket = ceil(delay_days / slab_in_days)`, `applicable_commission_percent = max(max_pct − bucket × reduction_pct, min_pct)`
      6. `commission_amount = commission_payable_base × applicable_commission_percent / 100`
      7. `gst_on_commission = commission_amount × Decimal("0.18")`; `final_line_claim_amount = commission_amount + gst_on_commission`
    - No I/O — pure function only
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 1.4 Write property tests for `CommissionCalculator` — Properties 1–5
    - Create `backend/tests/unit/test_commission_calculator_properties.py`
    - **Property 1: Net Amount Floor Invariant** — `net_amount ≥ 0` and equals `max(0, bill−deducted−tds)` for all non-negative inputs
    - **Property 2: Commission Payable Base Identity** — `commission_payable_base = net_amount + tds + deducted` for all inputs; corollary when both zero equals `bill_amount_excl_gst`
    - **Property 3: On-Time Payment Receives Maximum Commission** — when `payment_clearing_date ≤ due_date`, result equals `max_commission_percent`
    - **Property 4: Commission Percent Floor — Delayed Payments** — when `payment_clearing_date > due_date`, result is in `[min_commission_percent, max_commission_percent]`
    - **Property 5: GST Round-Trip** — `gst_on_commission = commission_amount × 0.18` and `final_line_claim_amount = commission_amount × 1.18`
    - Use `amount_strategy`, `percent_strategy`, `days_strategy`, `date_strategy` generators from design
    - `max_examples=200` per test; use `assume()` to constrain `min_pct ≤ max_pct` and date ordering
    - _Requirements: 3.2, 3.3, 3.5, 3.6, 3.8, 3.9, 22.1–22.7_

  - [x] 1.5 Create `ClaimAuditEntry` dataclass and repository interfaces
    - Create `src/domain/entities/claim_audit_entry.py` with `ClaimAuditEntry` dataclass
    - Create `src/domain/repositories/commission_claim/__init__.py`
    - Create `IClaimHeaderRepository`, `IClaimLineRepository`, `IClaimAuditRepository` abstract classes in `src/domain/repositories/commission_claim/`
    - Add `ClaimTotals` and `ClaimFilterParams` value objects
    - _Requirements: 14.1, 14.2, 14.3_

- [x] 2. Infrastructure layer — DB models and Alembic migration
  - [x] 2.1 Create SQLAlchemy ORM models for all four claim tables
    - Create `src/infrastructure/database/models/commission_claim/commission_claim_model.py`
    - Implement `ClaimHeaderModel(BaseModel)` with all columns, indexes, and FK to `vendors.id`
    - Implement `ClaimLineModel(BaseModel)` with all columns, `uq_claim_line_invoice` unique constraint, and CASCADE FK to `claim_headers.id`
    - Implement `ClaimAuditLogModel(BaseModel)` with JSONB `field_changes`, append-only intent
    - Implement `ClaimNumberSequenceModel(BaseModel)` with unique `financial_year` column
    - Register models in existing `src/infrastructure/database/models/__init__.py`
    - _Requirements: 1.1, 4.1, 13.3, 14.1_

  - [x] 2.2 Write Alembic migration to create claim tables and drop old stub
    - Create `src/infrastructure/database/migrations/versions/xxxx_add_commission_claim_tables.py`
    - Create tables: `claim_headers`, `claim_lines`, `claim_audit_logs`, `claim_number_sequences`
    - Add all indexes and constraints from design (composite index, unique constraint, FK with ON DELETE CASCADE)
    - Drop old stub `commission_claims` table in the same migration
    - _Requirements: 13.3_

  - [x] 2.3 Implement `ClaimHeaderRepositoryImpl` and `ClaimLineRepositoryImpl`
    - Create `src/infrastructure/database/repositories/commission_claim/claim_header_repository_impl.py`
    - Implement all `IClaimHeaderRepository` methods: `get_by_id`, `create`, `update`, `list_by_vendor`, `list_all`, `list_pending_for_user`
    - Create `src/infrastructure/database/repositories/commission_claim/claim_line_repository_impl.py`
    - Implement all `IClaimLineRepository` methods: `get_by_id`, `list_by_claim`, `create`, `update`, `delete`, `sum_totals`
    - _Requirements: 4.1, 4.2, 12.1, 12.2_

  - [x] 2.4 Implement `ClaimNumberSequenceService` and `ClaimAuditRepositoryImpl`
    - Create `src/infrastructure/database/repositories/commission_claim/claim_number_sequence_service.py`
    - Implement `next_claim_number(session)` using `SELECT ... FOR UPDATE` on `claim_number_sequences`
    - Compute Indian financial year (April–March) and format `CL/YYYY-YY/NNN` (zero-pad to 3 digits minimum, extend naturally for 1000+)
    - Create `src/infrastructure/database/repositories/commission_claim/claim_audit_repository_impl.py`
    - Implement append-only `create` and `list_by_claim`; expose no `update`/`delete` methods
    - _Requirements: 6.2, 6.3, 13.1, 13.2, 13.4, 14.3_

  - [x] 2.5 Write property test for claim number generation — Property 7
    - **Property 7: Claim Number Format Invariant** — for any sequence integer ≥ 1, generated number matches `^CL/\d{4}-\d{2}/\d{3,}$`
    - Also assert immutability: calling `next_claim_number` a second time on the same claim (claim_number already set) returns the existing number unchanged
    - _Requirements: 6.2, 6.3, 13.1, 13.4_

- [x] 3. Checkpoint — domain and infrastructure baseline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Application service — core lifecycle and line management
  - [x] 4.1 Scaffold `CommissionClaimService` with dependency injection
    - Create `src/application/services/commission_claim_service.py`
    - Define class with `__init__(self, session, audit_service, workflow_engine)`
    - Wire private repo instances: `ClaimHeaderRepositoryImpl`, `ClaimLineRepositoryImpl`, `ClaimAuditRepositoryImpl`, `ClaimNumberSequenceService`
    - _Requirements: 1.1_

  - [x] 4.2 Implement `create_claim` use case
    - Create `ClaimHeader` entity with status `Draft`, `claim_number=None`, `claim_date=utc today`
    - Persist via `ClaimHeaderRepositoryImpl.create`
    - Write audit entry for `Create` action immediately after persist
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

  - [x] 4.3 Implement `add_invoice_line` use case with all three pre-condition validations
    - Validate `invoice.invoice_status == "Payment Cleared"` (reject if "Settled" with exact error message)
    - Validate active Vendor-Customer Mapping exists for the invoice's `vendor_id`/`customer_id`
    - Validate active Agreement Master exists for `vendor_id`/`product_detail_id` within date range
    - Validate `payment_clearing_date ≥ invoice_date`; raise `ValueError` if not
    - Resolve `due_date` from Agreement `credit_days` or accept `due_date_override`
    - Invoke `CommissionCalculator.calculate()` and persist all 7 formula outputs
    - Recalculate header totals in same DB transaction (call `_recalculate_header_totals`)
    - Write audit entry for `Line Added` action
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.10, 3.11, 3.12, 4.1, 4.2_

  - [x] 4.4 Write property test for header totals — Property 6
    - **Property 6: Header Totals Equal Sum of Lines** — for any list of `ClaimLine` objects, after `_recalculate_header_totals`, header totals equal sums of corresponding line fields
    - Test all six aggregate fields: `total_claim_amount`, `total_commission_amount`, `total_gst_amount`, `total_tds_amount`, `total_ld_amount`, `total_retention_amount`
    - Test with `st.lists(amount_strategy, min_size=0, max_size=20)` covering empty list (all zeros)
    - _Requirements: 4.1, 4.2_

  - [x] 4.5 Implement `update_line_fields` and `remove_line` use cases
    - `update_line_fields`: accept `LineUpdateRequest` with partial fields; recalculate commission if `amount_deducted`, `tds_value`, or `payment_clearing_date` changed; recalculate header totals; write `Line Edited` audit entry only for changed fields
    - `remove_line`: delete line from DB; recalculate header totals in same transaction; write audit entry
    - _Requirements: 3.1, 4.1, 4.2, 10.1, 10.2, 10.3_

  - [x] 4.6 Implement `upload_pod` use case
    - Set `pod_document_id` on the line and write a `Field Edited` audit entry
    - Only allow when claim is in `Draft` or `Referred Back` status
    - _Requirements: 5.1, 5.3_

- [x] 5. Application service — submission, workflow actions, and post-closure
  - [x] 5.1 Implement `submit_claim` use case
    - Guard: only original initiator or Administrator can submit (return 403 otherwise)
    - Validate claim status is `Draft` or `Referred Back`; validate ≥ 1 line exists; validate all lines have `pod_document_id`
    - If `claim_number` is null, call `ClaimNumberSequenceService.next_claim_number()` inside UoW
    - Call `WorkflowEngine.start_workflow("claim_approval", "commission_claim", claim_id, ...)` and store returned `workflow_instance_id`
    - Set status to `Pending`; write `Submitted` audit entry (actor, timestamp, status transition)
    - _Requirements: 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9_

  - [x] 5.2 Write property test for claim number null at Draft creation — Property 11
    - **Property 11: Claim Number Null at Draft Creation** — for any valid `create_claim` call, resulting `ClaimHeader.claim_number` is `None` before first submission
    - _Requirements: 1.2, 6.3_

  - [x] 5.3 Implement `execute_workflow_action` use case (approve / refer-back / reject)
    - Validate non-empty `remarks`; reject with `ValueError` if empty
    - Call `WorkflowEngine.execute_action(instance_id, action_code, remarks)` to check eligibility
    - Determine if this is an intermediate or final approval using `WorkflowEngine.get_workflow_status`
    - Apply transition via `CLAIM_TRANSITIONS` map; raise `ValueError` for invalid transitions
    - On final approve: set status `Closed`, call `_run_post_closure`
    - On refer-back: set status `Referred Back`, notify original initiator
    - On reject: set status `Rejected`
    - Write audit entry for every action (actor, timestamp, from_status, to_status, step_name, remarks)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 11.1, 11.2_

  - [x] 5.4 Write property tests for status transition gating — Properties 8, 9
    - **Property 8: Status Transition Gating** — for any `(initial_status, action)` pair, if transition is in `CLAIM_TRANSITIONS`, result is in `ClaimStatus` value set; otherwise a `ValueError` is raised
    - **Property 9: Terminal State Immutability** — for any action applied to `Closed` or `Rejected`, a `ValueError` is always raised and status remains unchanged
    - Use `st.sampled_from(list(ClaimStatus))` and `st.sampled_from([...action codes...])`, `max_examples=300`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 22.8, 22.9_

  - [x] 5.5 Implement `_run_post_closure` private method
    - For each claim line, get `InvoiceHeaderModel` and set `invoice_status = "Settled"`; skip and log warning if already `Settled`
    - Fetch `VendorModel.gstn_number`; if matches `[A-Z0-9]{15}`, set `gstn_verification_status = "Verified"`, else `"Failed"`
    - Send HO Finance email notification (via existing notification service) with Claim Number and `total_claim_amount`
    - Write `Closed` audit entry
    - _Requirements: 9.1, 9.2, 9.4, 9.6_

  - [x] 5.6 Implement `update_payment_clearing_date`, `upload_gst_invoice`, and `record_sap_booking`
    - `update_payment_clearing_date`: only when claim is `Pending` and user is Finance-step approver or Admin; validate new date ≥ invoice date; recalculate commission for that line; recalculate header totals; write `Field Edited` audit entry with old/new values
    - `upload_gst_invoice`: only when `gstn_verification_status = "Verified"` and claim is `Closed`; persist `gst_invoice_number` and `gst_invoice_upload_date`; write audit entry
    - `record_sap_booking`: persist `sap_p2p_booking_reference` on Closed claim; write `SAP Booking Reference Recorded` audit entry
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.2, 9.3, 9.5_

  - [x] 5.7 Write property test for settled invoice pre-condition rejection — Property 10
    - **Property 10: Settled Invoice Pre-Condition Rejection** — for any invoice with `invoice_status = "Settled"`, `add_invoice_line` raises an error with message `"Invoice is already settled."` regardless of other attributes
    - Use `st.fixed_dictionaries` to build mock invoice objects with `invoice_status = "Settled"` and random other fields
    - _Requirements: 2.1, 22.10_

- [x] 6. Application service — views and list operations
  - [x] 6.1 Implement `get_claim_detail`, `list_claims`, and `get_claim_audit` use cases
    - `list_claims`: vendor-scoped for Liaisoning Agent, all claims for Admin; use `list_by_vendor` or `list_all` accordingly
    - `get_claim_detail`: return header + lines + workflow_status + available_actions
    - `get_claim_audit`: return audit entries in ascending timestamp order; only original initiator or Admin can access
    - _Requirements: 12.1, 12.2, 12.3, 14.4_

  - [x] 6.2 Implement `get_approval_queue`, `get_mis_pending`, `get_mis_history`, and `export_mis`
    - `get_approval_queue`: return `Pending` claims where current user is eligible approver for current step (via `list_pending_for_user`); Admin sees all pending claims; ordered by submission date ascending
    - `get_mis_pending`: return non-terminal claims (Draft, Pending, Referred Back) with status label `"Pending - <step_name>"` for Pending claims; support vendor/date-range/claim_number filters
    - `get_mis_history`: return terminal claims (Closed, Rejected) with same filters plus Final Decision Date
    - `export_mis`: produce Excel bytes (openpyxl) with one header row and one data row per claim, including full per-line commission breakdown
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 16.1, 16.2, 16.3, 17.1, 17.2, 17.3_

- [x] 7. Checkpoint — application service complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. API layer — FastAPI endpoints and Pydantic schemas
  - [x] 8.1 Create Pydantic v2 schemas module
    - Create `src/api/v1/endpoints/commission_claim/schemas.py`
    - Implement all request/response schemas from design: `ClaimCreateRequest`, `AddInvoiceLineRequest`, `LineUpdateRequest`, `WorkflowActionRequest`, `PaymentClearingDateRequest`, `SAPBookingRequest`, `ClaimLineResponse`, `ClaimHeaderResponse`, `ClaimDetailResponse`, `ClaimListResponse`, `ClaimAuditEntryResponse`, `MISFilterParams`
    - _Requirements: 19.2, 20.2_

  - [x] 8.2 Implement FastAPI controller for claim lifecycle and line management
    - Create `src/api/v1/endpoints/commission_claim/controller.py`
    - Implement endpoints: `POST /claims`, `GET /claims`, `GET /claims/{id}`, `GET /claims/{id}/audit`
    - Implement line endpoints: `POST /claims/{id}/lines`, `PATCH /claims/{id}/lines/{line_id}`, `DELETE /claims/{id}/lines/{line_id}`, `POST /claims/{id}/lines/{line_id}/pod`
    - All endpoints use `require_permission()` FastAPI dependency — no hardcoded role names
    - Catch `ValueError` from service and return `400 Bad Request`; let `require_permission()` return `403`
    - _Requirements: 1.1, 1.4, 2.1–2.5, 3.11, 4.1, 5.1–5.3, 12.3, 12.5_

  - [x] 8.3 Implement FastAPI controller for workflow actions and post-closure endpoints
    - Add endpoints: `POST /claims/{id}/submit`, `POST /claims/{id}/approve`, `POST /claims/{id}/refer-back`, `POST /claims/{id}/reject`
    - Add endpoints: `PATCH /claims/{id}/lines/{line_id}/payment-clearing-date`, `PATCH /claims/{id}/sap-booking`, `POST /claims/{id}/gst-invoice`
    - Add view endpoints: `GET /claims/approval-queue`, `GET /claims/mis/pending`, `GET /claims/mis/history`, `GET /claims/mis/pending/export`, `GET /claims/mis/history/export`
    - Register the router in `src/api/v1/router.py`
    - _Requirements: 6.4, 7.1–7.7, 8.1–8.5, 9.3, 9.5, 12.4, 15.1–15.4, 16.1–16.3, 17.1–17.3_

- [x] 9. RBAC permission seeding
  - [x] 9.1 Update `seed_rbac.py` with all claim permissions and role assignments
    - Add 10 permission entries to `DEFAULT_PERMISSIONS`: `menu.claims`, `menu.claims_mis`, `claims.create`, `claims.list`, `claims.view`, `claims.submit`, `claims.approve`, `claims.reject`, `claims.refer_back`, `claims.export`
    - Assign all 10 to `ADMIN` role
    - Create `LIAISONING_AGENT` role with `menu.claims`, `claims.create`, `claims.list`, `claims.view`, `claims.submit`
    - Create `L1_VERIFIER` role with `menu.claims`, `menu.claims_mis`, `claims.list`, `claims.view`, `claims.approve`, `claims.reject`, `claims.refer_back`
    - Create `L2_FINANCE` role with same as L1 plus `claims.export`
    - Script MUST be idempotent (use `INSERT ... ON CONFLICT DO NOTHING` pattern)
    - _Requirements: 18.1, 18.2, 18.3_

- [x] 10. Frontend — models, schemas, API client, and React Query hooks
  - [x] 10.1 Create TypeScript interfaces and Zod schemas
    - Create `frontend/src/features/commission-claims/models/claim.types.ts`
    - Implement all interfaces: `ClaimHeader`, `ClaimLine`, `ClaimDetail`, `ApprovalQueueItem`, `MISItem`
    - Create `frontend/src/features/commission-claims/schemas/claimSchema.ts`
    - Implement all Zod schemas: `addLineSchema`, `workflowActionSchema`, `sapBookingSchema`, `misFilterSchema`
    - Export `STATUS_SEVERITY` constant: Draft→info, Pending→warning, Referred Back→warning, Closed→success, Rejected→danger
    - _Requirements: 19.4, 20.4_

  - [x] 10.2 Create Axios API client module
    - Create `frontend/src/features/commission-claims/api/claimApi.ts`
    - Implement typed functions for all 20 REST endpoints: `create`, `list`, `getDetail`, `getAudit`, `addLine`, `updateLine`, `removeLine`, `uploadPod`, `submit`, `approve`, `referBack`, `reject`, `updatePaymentClearingDate`, `recordSapBooking`, `uploadGstInvoice`, `getApprovalQueue`, `getMisPending`, `getMisHistory`, `exportMisPending`, `exportMisHistory`
    - _Requirements: 19.1, 20.1, 21.1_

  - [x] 10.3 Implement React Query hooks
    - Create `frontend/src/features/commission-claims/hooks/useClaims.ts`: `useClaims`, `useCreateClaim`, `useSubmitClaim`
    - Create `frontend/src/features/commission-claims/hooks/useClaimDetail.ts`: `useClaimDetail`, `useWorkflowAction`, `useAddLine`, `useUpdateLine`, `useRemoveLine`, `useUploadPod`, `useUpdatePaymentClearingDate`
    - Create `frontend/src/features/commission-claims/hooks/useApprovalQueue.ts`: `useApprovalQueue`
    - Create `frontend/src/features/commission-claims/hooks/useMIS.ts`: `useMISPending`, `useMISHistory`, `useExportMIS`
    - All mutations invalidate relevant query keys on success
    - _Requirements: 19.3, 20.3, 21.4_

- [x] 11. Frontend — shared components
  - [x] 11.1 Implement `ClaimLineTable` and `ClaimHeaderTotalsPanel` components
    - Create `frontend/src/features/commission-claims/components/ClaimLineTable.tsx`
    - PrimeReact `DataTable` with all columns from Req 19.2; `stripedRows`; `paginator`
    - Create `frontend/src/features/commission-claims/components/ClaimHeaderTotalsPanel.tsx`
    - Display all 6 header totals live-updating; format as currency
    - _Requirements: 19.2, 19.3_

  - [x] 11.2 Implement `ClaimActionDialog` and `PODUploadCell` components
    - Create `frontend/src/features/commission-claims/components/ClaimActionDialog.tsx`
    - PrimeReact `Dialog` with `InputTextarea` for remarks; disable confirm button when remarks empty; support Approve/Refer Back/Reject actions
    - Create `frontend/src/features/commission-claims/components/PODUploadCell.tsx`
    - PrimeReact `FileUpload` or upload button per line; shows filename if `pod_document_id` is set
    - _Requirements: 5.1, 7.5, 20.3_

- [x] 12. Frontend — pages and routing
  - [x] 12.1 Implement `CreateClaimPage` and `ClaimDetailPage`
    - Create `frontend/src/features/commission-claims/pages/CreateClaimPage.tsx`
    - "Add Invoice Line" dialog using `addLineSchema` / `useAddLine`; shows `ClaimLineTable` and `ClaimHeaderTotalsPanel`; Submit button calls `useSubmitClaim`
    - Show status `Tag` severity per `STATUS_SEVERITY` map (Draft→info, Referred Back→warning)
    - Create `frontend/src/features/commission-claims/pages/ClaimDetailPage.tsx`
    - Render `payment_clearing_date` as editable `Calendar` only when `workflowStatus.step_code === "FINANCE_REVIEW"` and user has `claims.approve`; otherwise read-only
    - Show available actions (Approve/Refer Back/Reject) via `ClaimActionDialog`
    - _Requirements: 19.1–19.5, 20.3, 20.5_

  - [x] 12.2 Implement `ApprovalQueuePage`, `MISPendingPage`, and `MISHistoryPage`
    - Create `frontend/src/features/commission-claims/pages/ApprovalQueuePage.tsx`
    - PrimeReact `DataTable` with `stripedRows`, `paginator`, `rows={10}`, columns per Req 20.2; row click navigates to `ClaimDetailPage`
    - Create `frontend/src/features/commission-claims/pages/MISPendingPage.tsx`
    - `DataTable` with `filterDisplay="row"` for Vendor, Claim Date, Claim Number; status label `"Pending - <step_name>"`; Export button behind `PermissionGate permission="claims.export"`
    - Create `frontend/src/features/commission-claims/pages/MISHistoryPage.tsx`
    - Same structure as MIS Pending plus Final Decision Date column
    - _Requirements: 20.1, 20.2, 20.4, 21.1–21.5_

  - [x] 12.3 Create route definitions and barrel export
    - Create `frontend/src/features/commission-claims/routes/claimRoutes.tsx`
    - Wrap each page in `PrivateRoute` with correct `menuKey` (claims or claims_mis)
    - Register `renderClaimRoutes()` in the app router
    - Create `frontend/src/features/commission-claims/index.ts` barrel exporting all public API
    - _Requirements: 19.1, 20.1, 21.1_

- [x] 13. Final checkpoint — full integration
  - Ensure all unit and property-based tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP — but all 11 correctness properties should be covered before the feature goes to production
- Property tests use Hypothesis 6.155.2 already in `pyproject.toml` — no new dependency needed
- All backend code is Python; all frontend code is TypeScript
- The `_recalculate_header_totals` call MUST always run inside the same `UnitOfWork` transaction as the line change — never outside
- The `ClaimAuditRepositoryImpl` has no `update()`/`delete()` methods — immutability is enforced at the interface level
- `require_permission()` is the only access-control mechanism — no hardcoded role names anywhere in claim code
- The old stub `commission_claims` table is dropped in the same Alembic migration that creates the four new tables

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.5"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 4, "tasks": ["2.5", "4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4", "4.5", "4.6"] },
    { "id": 7, "tasks": ["5.1", "6.1"] },
    { "id": 8, "tasks": ["5.2", "5.3"] },
    { "id": 9, "tasks": ["5.4", "5.5", "5.6"] },
    { "id": 10, "tasks": ["5.7", "6.2"] },
    { "id": 11, "tasks": ["8.1", "9.1"] },
    { "id": 12, "tasks": ["8.2"] },
    { "id": 13, "tasks": ["8.3"] },
    { "id": 14, "tasks": ["10.1"] },
    { "id": 15, "tasks": ["10.2"] },
    { "id": 16, "tasks": ["10.3"] },
    { "id": 17, "tasks": ["11.1", "11.2"] },
    { "id": 18, "tasks": ["12.1", "12.2"] },
    { "id": 19, "tasks": ["12.3"] }
  ]
}
```
