# Requirements Document

## Introduction

The Commission Claim Management feature enables Liaisoning Agents (Vendors) to raise
commission claims against payment-cleared invoices. The system automatically calculates
commission amounts using Agreement Master slab rules, routes each claim through a
configurable multi-level approval workflow, and closes the claim once all approvals
complete — at which point covered invoices are marked Settled and an SAP P2P booking
reference is recorded.

This feature integrates with the existing Dynamic Approval Workflow Engine, Enterprise
RBAC system, and all relevant Master data entities (Vendor, Customer, Invoice, Agreement
Master, Vendor-Customer Mapping) already present in the codebase.

---

## Glossary

- **Claim**: A commission claim request raised by a Liaisoning Agent against one or more
  payment-cleared invoices.
- **Claim_Header**: The top-level aggregate that owns one or more Claim Lines and tracks
  overall status, totals, and post-closure fields.
- **Claim_Line**: A single invoice-level row within a Claim Header. Stores all calculated
  commission fields for one invoice.
- **Commission_Calculator**: The pure domain service that computes all 7 formula steps
  from Agreement Master slab parameters.
- **Workflow_Engine**: The existing dynamic approval workflow orchestration service at
  `src/application/services/workflow/workflow_engine.py`.
- **Claim_Service**: The application-layer service that orchestrates claim CRUD,
  commission calculation, and workflow integration.
- **Claim_Repository**: The repository interface in the domain layer for Claim Header
  persistence.
- **Claim_Line_Repository**: The repository interface in the domain layer for Claim Line
  persistence.
- **Liaisoning_Agent**: The Vendor user who creates and submits claims. In the RBAC system
  this actor holds a role seeded with `claims.create`, `claims.submit`, `claims.view`
  permissions scoped to their own vendor.
- **L1_Verifier**: The first-level workflow approver. Holds a role with `claims.approve`,
  `claims.reject`, `claims.refer_back` permissions.
- **L2_Finance_User**: The second-level workflow approver. Holds a role with
  `claims.approve`, `claims.reject`, `claims.refer_back` permissions plus the ability to
  edit Payment Clearing Date on claim lines.
- **Administrator**: Holds all claim permissions and full workflow configuration access.
- **POD_Document**: Proof-of-Delivery document — one mandatory upload per Claim Line
  before submission is allowed.
- **Due_Date**: Invoice Date + Credit Days (from the matched Agreement Master); can be
  manually overridden by the Liaisoning Agent on the Claim Line.
- **Delay_Days**: Payment Clearing Date − Due Date (whole calendar days; negative or zero
  means on-time/early payment).
- **Slab**: One bucket in the commission-reduction schedule; length is `slab_in_days` from
  the Agreement Master.
- **Net_Amount**: Bill Amount (excl. GST) − Amount Deducted − TDS Value, floored at 0.
- **Commission_Payable_Base**: Net Amount + TDS Value + Amount Deducted (algebraically
  equals Bill Amount excl. GST when Net Amount ≥ 0).
- **Applicable_Commission_Percent**: The commission rate derived from the Agreement Master
  slab rules given the Delay Days.
- **Commission_Amount**: Commission Payable Base × Applicable Commission %.
- **GST_on_Commission**: Commission Amount × 18% (fixed, non-editable).
- **Final_Line_Claim_Amount**: Commission Amount + GST on Commission.
- **MIS_Pending_View**: List of all non-terminal claims (Draft, Pending, Referred Back).
- **MIS_History_View**: List of all terminal claims (Closed, Rejected).
- **SAP_P2P_Booking_Reference**: The SAP purchase-to-pay document reference recorded by
  Finance after payment disbursement is booked in SAP.
- **GSTN**: The 15-character alphanumeric GST Identification Number of the vendor.
- **Approval_Queue**: The view showing claims awaiting action by the currently logged-in
  approver.

---

## Requirements

---

### Requirement 1: Claim Draft Creation

**User Story:** As a Liaisoning Agent, I want to create a commission claim draft, so that I
can collect invoice lines before submitting for approval.

#### Acceptance Criteria

1. WHEN a Liaisoning Agent with the `claims.create` permission sends a create-claim
   request, THE Claim_Service SHALL create a Claim_Header with status `Draft`, recording
   the authenticated user's Vendor Id as the claim's owner.
2. THE Claim_Service SHALL NOT assign a Claim Number at draft creation — the Claim Number
   field SHALL remain null until the first submission.
3. THE Claim_Service SHALL record `Claim Date` as the UTC date of draft creation.
4. WHEN a user without the `claims.create` permission attempts to create a claim, THE
   Claim_Service SHALL return an authorization error.
5. THE Claim_Service SHALL record an immutable audit entry for the `Create` action
   immediately after the draft is persisted.

---

### Requirement 2: Invoice Pre-Condition Validation

**User Story:** As a Liaisoning Agent, I want the system to validate invoices before
adding them to a claim, so that only eligible invoices are claimed.

#### Acceptance Criteria

1. WHEN a Liaisoning Agent requests to add an invoice line to a Claim, THE Claim_Service
   SHALL verify that the invoice's `invoice_status` equals `Payment Cleared`; IF the
   status is `Settled`, THEN THE Claim_Service SHALL return the error
   `"Invoice is already settled."` and block the addition.
2. WHEN a Liaisoning Agent requests to add an invoice line to a Claim, THE Claim_Service
   SHALL verify that an active Vendor-Customer Mapping exists for the invoice's
   `vendor_id` and `customer_id` as of the invoice date; IF no active mapping exists,
   THEN THE Claim_Service SHALL return a descriptive error and block the addition.
3. WHEN a Liaisoning Agent requests to add an invoice line to a Claim, THE Claim_Service
   SHALL verify that an active Agreement Master exists for the invoice's `vendor_id` and
   `product_detail_id` where the invoice date falls within `from_date` and `to_date`;
   IF no matching active agreement exists, THEN THE Claim_Service SHALL return a
   descriptive error and block the addition.
4. IF all three pre-conditions pass, THEN THE Claim_Service SHALL create a Claim_Line,
   populate `Due_Date` as Invoice Date + Credit Days from the matched Agreement Master,
   and immediately trigger commission calculation for that line.
5. WHERE a Liaisoning Agent supplies a manual override for `Due_Date`, THE Claim_Service
   SHALL accept the override value instead of the Agreement-derived date and recalculate
   commission accordingly.

---

### Requirement 3: Commission Calculation (7-Step Formula)

**User Story:** As a Liaisoning Agent, I want the system to automatically calculate the
commission for each invoice line, so that I do not need to compute amounts manually.

#### Acceptance Criteria

1. WHEN a Claim_Line is created or WHEN `amount_deducted`, `tds_value`, or
   `payment_clearing_date` is updated on an existing Claim_Line, THE Commission_Calculator
   SHALL execute all 7 formula steps and persist the results against the Claim_Line.

2. THE Commission_Calculator SHALL compute `Net_Amount` as
   `bill_amount_excl_gst − amount_deducted − tds_value`, floored at `0` if the
   result is negative.

3. THE Commission_Calculator SHALL compute `Commission_Payable_Base` as
   `Net_Amount + tds_value + amount_deducted`.

4. THE Commission_Calculator SHALL compute `Delay_Days` as
   `payment_clearing_date − due_date` in whole calendar days.

5. WHEN `Delay_Days` is less than or equal to `0`, THE Commission_Calculator SHALL set
   `Applicable_Commission_Percent` to `max_commission_percent` from the Agreement Master.

6. WHEN `Delay_Days` is greater than `0`, THE Commission_Calculator SHALL compute
   `Bucket = CEILING(Delay_Days / slab_in_days)`, then set
   `Applicable_Commission_Percent = MAX(max_commission_percent − Bucket × reduction_percent,
   min_commission_percent)`.

7. THE Commission_Calculator SHALL compute `Commission_Amount` as
   `Commission_Payable_Base × Applicable_Commission_Percent`.

8. THE Commission_Calculator SHALL compute `GST_on_Commission` as
   `Commission_Amount × 18%`. THE Claim_Service SHALL NOT allow the GST rate to be
   overridden under any circumstance.

9. THE Commission_Calculator SHALL compute `Final_Line_Claim_Amount` as
   `Commission_Amount + GST_on_Commission`.

10. THE Claim_Service SHALL save all 7 intermediate values (Net_Amount,
    Commission_Payable_Base, Delay_Days, Applicable_Commission_Percent,
    Commission_Amount, GST_on_Commission, Final_Line_Claim_Amount) to the Claim_Line
    row for audit and display.

11. IF `payment_clearing_date` is earlier than `invoice_date` on the same invoice,
    THEN THE Claim_Service SHALL return a validation error and block the save.

12. `LD_Charges` and `Retention_Amount` SHALL be stored on the Claim_Line as display-only
    values. THE Commission_Calculator SHALL NOT include either field in any formula step.

---

### Requirement 4: Claim Header Totals Maintenance

**User Story:** As a Liaisoning Agent, I want the claim header totals to reflect the live
sum of all lines, so that I can review the overall claim amount before submitting.

#### Acceptance Criteria

1. WHEN a Claim_Line is added, updated, or removed, THE Claim_Service SHALL recalculate
   and persist the following Claim_Header aggregate totals:
   `total_claim_amount` (sum of `Final_Line_Claim_Amount`),
   `total_commission_amount` (sum of `Commission_Amount`),
   `total_gst_amount` (sum of `GST_on_Commission`),
   `total_tds_amount` (sum of `tds_value`),
   `total_ld_amount` (sum of `ld_charges`),
   `total_retention_amount` (sum of `retention_amount`).
2. THE Claim_Service SHALL perform the total recalculation within the same database
   transaction as the Claim_Line change.

---

### Requirement 5: POD Document Upload per Claim Line

**User Story:** As a Liaisoning Agent, I want to attach a Proof-of-Delivery document to
each invoice line, so that the approver can verify the delivery before approving.

#### Acceptance Criteria

1. THE Claim_Service SHALL allow exactly one POD_Document to be attached per Claim_Line.
2. WHEN a Liaisoning Agent requests to submit a claim, THE Claim_Service SHALL verify that
   every Claim_Line on that claim has a non-null `pod_document_id`; IF any line is missing
   a POD_Document, THEN THE Claim_Service SHALL return an error identifying the missing
   lines and block submission.
3. WHEN a Liaisoning Agent replaces a POD_Document on a Claim_Line in `Draft` or
   `Referred Back` status, THE Claim_Service SHALL update `pod_document_id` and record an
   immutable audit entry for the field change.

---

### Requirement 6: Claim Number Assignment and Submission

**User Story:** As a Liaisoning Agent, I want to submit my draft claim so that it enters
the approval workflow and receives a formal claim number.

#### Acceptance Criteria

1. WHEN a Liaisoning Agent with the `claims.submit` permission submits a Claim in `Draft`
   status, THE Claim_Service SHALL verify the claim has at least one Claim_Line; IF the
   claim has no lines, THEN THE Claim_Service SHALL return an error and block submission.
2. WHEN a Liaisoning Agent submits a Claim and a Claim Number has not yet been assigned,
   THE Claim_Service SHALL generate a Claim Number in the format `CL/YYYY-YY/NNN` where
   `YYYY-YY` is the current Indian financial year and `NNN` is a zero-padded sequential
   counter (e.g., `CL/2025-26/001`).
3. THE Claim_Service SHALL assign the Claim Number only once — subsequent resubmissions of
   the same Claim SHALL retain the original Claim Number.
4. WHEN the Claim_Service submits a claim, THE Workflow_Engine SHALL start a workflow
   instance for `entity_type = "commission_claim"` using the active
   `claim_approval` workflow definition, setting the claim status to `Pending` at Step 1.
5. IF no active `claim_approval` workflow definition is configured for the entity,
   THEN THE Claim_Service SHALL return an error and block submission.
6. WHEN submission succeeds, THE Claim_Service SHALL send an email notification to the
   eligible approver(s) at Step 1.
7. WHEN a Liaisoning Agent with the `claims.submit` permission submits a Claim in
   `Referred Back` status, THE Claim_Service SHALL route the resubmission back to Step 1
   of the workflow regardless of which step originally triggered the refer-back.
8. WHEN submission or resubmission succeeds, THE Claim_Service SHALL record an immutable
   audit entry for the `Submitted` action, capturing the actor, timestamp, and status
   transition.
9. WHEN a user who is not the original claim initiator and does not hold Administrator
   permissions attempts to submit a claim, THE Claim_Service SHALL return an authorization
   error.

---

### Requirement 7: Approval Workflow Actions

**User Story:** As an L1 Verifier or L2 Finance User, I want to approve, refer back, or
reject a pending claim, so that the claim moves to the next step or reaches a terminal
state.

#### Acceptance Criteria

1. WHEN an eligible approver with the `claims.approve` permission approves a Pending
   claim and a subsequent workflow step exists, THE Workflow_Engine SHALL advance the
   claim to `Pending` at the next step and send an email notification to the next-step
   approver(s).
2. WHEN an eligible approver with the `claims.approve` permission approves a Pending
   claim and no further workflow step exists, THE Claim_Service SHALL set the claim status
   to `Closed` and trigger the post-closure sequence defined in Requirement 9.
3. WHEN an eligible approver with the `claims.refer_back` permission refers back a Pending
   claim, THE Claim_Service SHALL set the claim status to `Referred Back` and notify the
   original initiator.
4. WHEN an eligible approver with the `claims.reject` permission rejects a Pending claim,
   THE Claim_Service SHALL set the claim status to `Rejected`. No further status
   transitions SHALL be allowed from `Rejected`.
5. THE Claim_Service SHALL require a non-empty `remarks` field for every approval,
   refer-back, or rejection action; IF remarks are empty, THEN THE Claim_Service SHALL
   return a validation error.
6. WHEN a user who is not the eligible approver for the current step and does not hold
   Administrator permissions attempts to approve, refer back, or reject a Pending claim,
   THE Claim_Service SHALL return an authorization error.
7. WHEN any approval, refer-back, or rejection action is completed, THE Claim_Service
   SHALL record an immutable audit entry capturing: actor, timestamp, from-status,
   to-status, workflow step name, and remarks.

---

### Requirement 8: Finance Approver Payment Clearing Date Edit

**User Story:** As an L2 Finance User, I want to edit the Payment Clearing Date on a
claim line while approving, so that the commission is recalculated with the correct
payment date.

#### Acceptance Criteria

1. WHILE a claim is at the Finance-designated workflow step, THE Claim_Service SHALL
   permit the assigned Finance approver (or Administrator) to update `payment_clearing_date`
   on any Claim_Line.
2. WHEN `payment_clearing_date` is updated on a Claim_Line, THE Commission_Calculator
   SHALL immediately recalculate all 7 commission formula steps for that line and persist
   the updated values.
3. WHEN a Finance approver edits `payment_clearing_date`, THE Claim_Service SHALL record
   an immutable audit entry with the old and new values of `payment_clearing_date` and
   the recalculated `Final_Line_Claim_Amount`.
4. WHEN `payment_clearing_date` is set to a value earlier than the invoice's `invoice_date`,
   THE Claim_Service SHALL return a validation error and discard the change.
5. WHEN a user who is not the current Finance-step approver and does not hold
   Administrator permissions attempts to edit `payment_clearing_date` on a Pending claim,
   THE Claim_Service SHALL return an authorization error.

---

### Requirement 9: Post-Closure Sequence

**User Story:** As an Administrator or Finance User, I want the system to automatically
settle invoices and enable GST and SAP booking steps once a claim closes, so that the
financial record is complete.

#### Acceptance Criteria

1. WHEN a claim transitions to `Closed` status, THE Claim_Service SHALL update the
   `invoice_status` of every invoice covered by the claim's Claim Lines to `Settled`.
2. WHEN a claim transitions to `Closed` status, THE Claim_Service SHALL verify the
   vendor's `gstn_number` is a 15-character alphanumeric string; IF valid, THE
   Claim_Service SHALL set `gstn_verification_status` to `Verified`; IF invalid or
   absent, THE Claim_Service SHALL set `gstn_verification_status` to `Failed` and block
   GST Invoice upload until the GSTN is corrected.
3. WHEN `gstn_verification_status` is `Verified`, THE Claim_Service SHALL permit the
   Liaisoning Agent to upload a GST Invoice document against the Claim_Header and record
   `gst_invoice_number` and `gst_invoice_upload_date`.
4. WHEN a Claim is `Closed`, THE Claim_Service SHALL send an email notification to the HO
   Finance team containing the Claim Number and `total_claim_amount` for SAP P2P booking.
5. WHEN Finance records an `sap_p2p_booking_reference` on a Closed claim, THE
   Claim_Service SHALL persist the value and record an immutable audit entry with the
   actor and timestamp.
6. IF an invoice covered by a claim is already in `Settled` status when the closure
   sequence runs (concurrent edge case), THEN THE Claim_Service SHALL skip that invoice's
   status update and log a warning rather than raising a hard error.

---

### Requirement 10: Referred-Back Claim Editing

**User Story:** As a Liaisoning Agent, I want to edit a referred-back claim and resubmit
it, so that I can address the approver's concerns and re-enter the approval workflow.

#### Acceptance Criteria

1. WHILE a claim is in `Referred Back` status, THE Claim_Service SHALL permit only the
   original initiator or an Administrator to edit claim line fields (`amount_deducted`,
   `tds_value`, `ld_charges`, `retention_amount`, `due_date`, `remarks`,
   `pod_document_id`).
2. WHEN any editable field on a `Referred Back` claim is changed, THE Claim_Service SHALL
   record an immutable audit entry capturing the field name, old value, and new value.
3. THE Claim_Service SHALL NOT record an audit entry for a field unless the new value
   differs from the old value.
4. WHEN a `Referred Back` claim is resubmitted, THE Claim_Service SHALL reset the workflow
   to Step 1, applying the same validation rules as the initial submission (at least one
   line, all POD documents present).

---

### Requirement 11: Claim Status Transition Invariants

**User Story:** As a system administrator, I want claim status transitions to follow the
defined state machine, so that no claim can reach an invalid state.

#### Acceptance Criteria

1. THE Claim_Service SHALL permit the following and only the following status transitions:
   `Draft → Pending` (submit),
   `Pending → Pending` (intermediate approve),
   `Pending → Closed` (final approve),
   `Pending → Referred Back` (refer back),
   `Pending → Rejected` (reject),
   `Referred Back → Pending` (resubmit).
2. IF an action would produce a transition not listed in criterion 1, THEN THE
   Claim_Service SHALL return an error and leave the claim status unchanged.
3. THE Claim_Service SHALL NOT allow any transition out of `Closed` status.
4. THE Claim_Service SHALL NOT allow any transition out of `Rejected` status.

---

### Requirement 12: RBAC and Data Visibility

**User Story:** As a system administrator, I want RBAC to enforce data visibility so that
each actor sees only the claims relevant to their role.

#### Acceptance Criteria

1. WHEN a Liaisoning Agent with the `claims.list` permission queries the claim list, THE
   Claim_Service SHALL return only claims whose `vendor_id` matches the authenticated
   user's vendor identity.
2. WHEN an Administrator with the `claims.list` permission queries the claim list, THE
   Claim_Service SHALL return all claims regardless of vendor.
3. WHEN a user without the `claims.view` permission requests claim details, THE
   Claim_Service SHALL return an authorization error.
4. WHEN an L1_Verifier or L2_Finance_User with `claims.approve` permission queries the
   Approval_Queue, THE Claim_Service SHALL return only claims where the authenticated user
   is the eligible approver for the current workflow step.
5. THE Claim_Service SHALL enforce all access controls via the existing
   `require_permission()` dependency — no hardcoded role names SHALL appear in claim
   endpoints.

---

### Requirement 13: Claim Number Format and Sequence

**User Story:** As a Finance user, I want claim numbers to follow a predictable format,
so that claims are traceable across financial years.

#### Acceptance Criteria

1. THE Claim_Service SHALL generate Claim Numbers in the format `CL/YYYY-YY/NNN` where
   `YYYY-YY` represents the Indian financial year (April to March) and `NNN` is a
   zero-padded three-digit sequential counter per financial year.
2. THE Claim_Service SHALL reset the sequence counter to `001` at the start of each new
   financial year (1 April).
3. THE Claim_Service SHALL guarantee uniqueness of Claim Numbers at the database level via
   a unique constraint on the `claim_number` column.
4. IF generating the next sequence number would exceed three digits (i.e., more than 999
   claims in a financial year), THEN THE Claim_Service SHALL extend the counter to four
   digits (e.g., `CL/2025-26/1000`) rather than raising an error.

---

### Requirement 14: Immutable Audit Trail

**User Story:** As an Administrator, I want a complete, tamper-proof audit trail of all
claim actions, so that I can trace the full history of any claim.

#### Acceptance Criteria

1. THE Claim_Service SHALL record an audit entry for each of the following actions:
   `Create` (draft created), `Line Added`, `Line Edited`, `Submitted`, `Approved`,
   `Referred Back`, `Rejected`, `Field Edited` (on Referred Back claim), `Closed`,
   `SAP Booking Reference Recorded`.
2. EACH audit entry SHALL capture: actor username, actor user ID, timestamp (UTC),
   `from_status`, `to_status`, workflow step name (where applicable), remarks (where
   applicable), and field-level old/new values (for field-edit events).
3. THE Claim_Service SHALL NOT provide any API endpoint or service method that updates
   or deletes an existing audit entry.
4. WHEN a user with the `claims.view` permission and who is either the original initiator
   or an Administrator requests the audit trail for a claim, THE Claim_Service SHALL
   return the complete list of audit entries for that claim in ascending timestamp order.

---

### Requirement 15: MIS Pending View

**User Story:** As an Administrator or Finance User, I want a paginated view of all
non-terminal claims with filtering and export, so that I can monitor the claims pipeline.

#### Acceptance Criteria

1. WHEN a user with the `menu.claims_mis` permission requests the MIS Pending view, THE
   Claim_Service SHALL return all claims whose status is one of `Draft`, `Pending`, or
   `Referred Back`, including Claim Number, Vendor Name, Claim Date, Status (with
   workflow step label for Pending claims), Total Claim Amount, and Total Commission
   Amount.
2. THE Claim_Service SHALL support filtering the MIS Pending view by Vendor (exact
   match), Claim Date range (start and end date), and Claim Number (partial text match).
3. WHEN a user with the `claims.export` permission requests an Excel export of the MIS
   Pending view, THE Claim_Service SHALL produce a workbook containing one header row and
   one data row per claim, including the full per-line commission breakdown for each claim.
4. WHILE displaying a Pending claim's status, THE Claim_Service SHALL provide a status
   label in the format `"Pending - <step_name>"` (e.g., `"Pending - L1 Verification"`)
   in addition to the raw `Pending` status code.

---

### Requirement 16: MIS History View

**User Story:** As an Administrator or Finance User, I want a paginated view of all
terminal claims with filtering and export, so that I can review completed and rejected
claims.

#### Acceptance Criteria

1. WHEN a user with the `menu.claims_mis` permission requests the MIS History view, THE
   Claim_Service SHALL return all claims whose status is `Closed` or `Rejected`,
   including the same columns as the MIS Pending view plus Final Decision Date.
2. THE Claim_Service SHALL support the same filtering capabilities for MIS History as for
   MIS Pending (Vendor, Claim Date range, Claim Number).
3. WHEN a user with the `claims.export` permission requests an Excel export of the MIS
   History view, THE Claim_Service SHALL produce a workbook with the same structure as
   the MIS Pending export, including the Final Decision Date column.

---

### Requirement 17: Approval Queue View

**User Story:** As an L1 Verifier or L2 Finance User, I want to see the claims pending
my action, so that I can efficiently work through my approval queue.

#### Acceptance Criteria

1. WHEN a user with the `claims.approve` permission requests the Approval_Queue, THE
   Claim_Service SHALL return only claims in `Pending` status where the authenticated user
   is the eligible approver for the current workflow step, ordered by submission date
   ascending.
2. EACH claim in the Approval_Queue response SHALL include Claim Number, Vendor Name,
   Claim Date, Total Claim Amount, current workflow step name, and submission date.
3. WHEN an Administrator requests the Approval_Queue, THE Claim_Service SHALL return all
   claims in `Pending` status across all workflow steps.

---

### Requirement 18: Permission Seeding

**User Story:** As an Administrator, I want all claim permissions pre-seeded in the RBAC
system, so that roles can be configured without manual permission creation.

#### Acceptance Criteria

1. THE system seed script SHALL create the following permissions if they do not already
   exist: `claims.create`, `claims.list`, `claims.view`, `claims.submit`,
   `claims.approve`, `claims.reject`, `claims.refer_back`, `claims.export`,
   `menu.claims`, `menu.claims_mis`.
2. THE system seed script SHALL assign all ten claim permissions to the `ADMIN` role.
3. THE system seed script SHALL be idempotent — running it multiple times SHALL NOT
   create duplicate permissions or role-permission assignments.

---

### Requirement 19: Frontend — Create and Draft Claim Page

**User Story:** As a Liaisoning Agent, I want a web page to create a draft claim and
manage its invoice lines, so that I can build my claim before submission.

#### Acceptance Criteria

1. THE Create_Claim_Page SHALL be accessible only to users whose RBAC menu permissions
   include `menu.claims`.
2. THE Create_Claim_Page SHALL display a PrimeReact DataTable of Claim Lines with columns:
   Invoice Number, Bill Amount, Amount Deducted, TDS Value, LD Charges, Retention Amount,
   Net Amount, Commission Payable Base, Due Date, Payment Clearing Date, Delay Days,
   Applicable Commission %, Commission Amount, GST on Commission, Final Line Claim Amount,
   POD Document, Remarks.
3. THE Create_Claim_Page SHALL display a live-updating summary panel showing all six
   Claim_Header totals (Total Claim Amount, Total Commission, Total GST, Total TDS, Total
   LD, Total Retention).
4. THE Create_Claim_Page SHALL use `Tag` severity `info` for `Draft` status and `warning`
   for `Referred Back` status.
5. THE Create_Claim_Page SHALL render within the Sakai layout with Emcure brand colors
   (#ED1C24 primary) and PrimeReact components exclusively.

---

### Requirement 20: Frontend — Approval Queue and Claim Review Page

**User Story:** As an L1 Verifier or L2 Finance User, I want a web page to view pending
claims and take approval actions, so that I can process the approval workflow efficiently.

#### Acceptance Criteria

1. THE Approval_Queue_Page SHALL be accessible only to users whose RBAC permissions
   include `claims.approve`.
2. THE Approval_Queue_Page SHALL display pending claims in a PrimeReact DataTable with
   `stripedRows`, `paginator`, and `rows={10}`, with columns: Claim Number, Vendor Name,
   Claim Date, Total Claim Amount, Step Name, Submission Date.
3. WHEN an approver selects a claim row, THE Approval_Queue_Page SHALL navigate to the
   Claim Detail view showing all claim lines, header totals, and available actions
   (Approve, Refer Back, Reject) via PrimeReact Button components.
4. THE Approval_Queue_Page SHALL use `Tag` severity `warning` for `Pending` and
   `Referred Back` statuses, `success` for `Closed`, and `danger` for `Rejected`.
5. WHERE the authenticated user is at the Finance workflow step, THE Claim_Detail_View
   SHALL render the `payment_clearing_date` field as an editable PrimeReact Calendar
   input per Claim Line; for all other steps, the field SHALL be read-only.

---

### Requirement 21: Frontend — MIS Pending and MIS History Pages

**User Story:** As an Administrator or Finance User, I want paginated MIS views with
Excel export, so that I can monitor and report on claims.

#### Acceptance Criteria

1. THE MIS_Pending_Page SHALL be accessible only to users whose RBAC menu permissions
   include `menu.claims_mis`.
2. THE MIS_Pending_Page SHALL display all non-terminal claims in a PrimeReact DataTable
   with `filterDisplay="row"` enabled for Vendor, Claim Date, and Claim Number columns.
3. THE MIS_History_Page SHALL display all terminal claims with the same filtering
   capabilities as the MIS_Pending_Page plus a Final Decision Date column.
4. WHERE a user has the `claims.export` permission, BOTH MIS pages SHALL render an Export
   button that triggers the Excel download including full per-line commission breakdowns.
5. BOTH MIS pages SHALL display the Status column using PrimeReact `Tag` components with
   the severity mapping: `Draft → info`, `Pending → warning`, `Referred Back → warning`,
   `Closed → success`, `Rejected → danger`.

---

### Requirement 22: Property-Based Correctness Properties

**User Story:** As a developer, I want property-based tests for the commission calculator
and claim state machine, so that edge cases are automatically discovered.

#### Acceptance Criteria

1. FOR ALL valid inputs where `bill_amount_excl_gst ≥ 0`, `amount_deducted ≥ 0`, and
   `tds_value ≥ 0`, THE Commission_Calculator SHALL produce `Net_Amount ≥ 0`.

2. FOR ALL valid inputs, THE Commission_Calculator SHALL produce
   `Commission_Payable_Base = Net_Amount + tds_value + amount_deducted`.

3. FOR ALL valid inputs where `amount_deducted = 0` and `tds_value = 0`, THE
   Commission_Calculator SHALL produce `Commission_Payable_Base = bill_amount_excl_gst`.

4. FOR ALL valid inputs where `Delay_Days ≤ 0`, THE Commission_Calculator SHALL produce
   `Applicable_Commission_Percent = max_commission_percent`.

5. FOR ALL valid inputs where `Delay_Days > 0` and `slab_in_days > 0`, THE
   Commission_Calculator SHALL produce
   `Applicable_Commission_Percent ≥ min_commission_percent`.

6. FOR ALL valid inputs where `Delay_Days > 0` and `slab_in_days > 0`, THE
   Commission_Calculator SHALL produce
   `Applicable_Commission_Percent ≤ max_commission_percent`.

7. FOR ALL valid commission calculation inputs, THE Commission_Calculator SHALL produce
   `Final_Line_Claim_Amount = Commission_Amount × 1.18` (round-trip of the 18% GST
   addition).

8. FOR ALL sequences of valid status transitions starting from `Draft`, THE Claim_Service
   SHALL never produce a claim status outside the set
   `{Draft, Pending, Referred Back, Closed, Rejected}`.

9. FOR ALL states in `{Closed, Rejected}`, THE Claim_Service SHALL reject any further
   status transition attempt and leave the claim status unchanged (terminal-state
   idempotence).

10. FOR ALL invoices in `Settled` status, THE Claim_Service SHALL reject pre-condition
    check 1 (Requirement 2.1) regardless of other invoice attributes.
