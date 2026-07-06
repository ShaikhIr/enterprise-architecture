# Implementation Plan: LACM Masters

## Overview

This plan implements the complete set of LACM master entities (Entity, Vendor, Customer, Product Master, Product Detail, Agreement, Vendor–Customer Mapping, Invoice Header/Line), the Claim Validation Triangle, bulk upload, and scheduled expiry jobs, following the existing backend layered Clean Architecture (Controller → Service → Repository Interface → Repository Implementation).

Implementation language: **Python 3.12** (FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Alembic, Celery), as specified in the design. Property-based tests use **Hypothesis** (`@settings(max_examples=100)`), each property in its own test module tagged `# Feature: lacm-masters, Property {n}: ...`.

Each master follows the module placement table in the design. Audit fields/logging (Req 20.1) come for free via `BaseModel`/`AuditMixin` and the existing `before_flush` listener. Authentication (Req 20.2) and RBAC (Req 20.3) are reused via `get_current_active_user` and `require_api_permission(...)` applied in every controller. No new roles are created.

Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP.

## Tasks

- [x] 1. Foundations and shared scaffolding
  - [x] 1.1 Create masters enums and master application exceptions
    - Add `src/domain/enums/masters.py` with `VendorStatus`, `CustomerStatus`, `CustomerType`, `ProductStatus`, `AgreementType`, `AgreementStatus`, `MappingStatus`, `InvoiceStatus` as `StrEnum`
    - Add `MasterValidationError(field, reason)`, `MasterConflictError(detail)`, `MasterNotFoundError(resource, id)` to `src/application/exceptions/application_exceptions.py`
    - _Requirements: 8.3_
  - [x] 1.2 Create shared masters pagination schema and package structure
    - Add generic `PaginatedResponse[T]` (`items`, `total`, `skip`, `limit`) to `src/api/v1/schemas/masters/common.py`
    - Create `masters/` package `__init__.py` files under domain entities, domain repositories, infrastructure models, infrastructure repositories, application services, and api schemas/endpoints
    - _Requirements: 1.9_

- [x] 2. Entity Master
  - [x] 2.1 Implement Entity domain entity, ORM model, and repository
    - Add `EntityEntity` dataclass (`src/domain/entities/masters/entity.py`) extending `BaseEntity`
    - Add `EntityModel(BaseModel)` (`src/infrastructure/database/models/masters/entity_model.py`): `entity_name` (255, not null, ci-unique), `short_code` (50), `company_code` (50, ci-unique), `is_active` (default true)
    - Add `IEntityRepository` port and `EntityRepositoryImpl` with trimmed case-insensitive uniqueness/search queries
    - _Requirements: 1.1_
  - [x] 2.2 Implement EntityService (CRUD, search, filter, dropdown)
    - Validate required/length rules, trimmed case-insensitive name/company-code uniqueness, partial update, pagination, search, active filter; default `is_active=true`
    - Implement `get_dropdown` returning only active entities with label `"{short_code} - {entity_name}"` and `Unknown` substitution
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.11, 1.12, 2.1, 2.2, 2.3, 2.4_
  - [x] 2.3 Implement Entity request/response schemas and controller
    - Pydantic v2 request/response schemas; `entity_controller.py` router with `require_api_permission` + `get_current_active_user`; pagination via `Query(0, ge=0)` / `Query(20, ge=1, le=100)`; map master exceptions to 422/409/404
    - _Requirements: 1.10, 20.2, 20.3_
  - [x] 2.4 Write property test for Entity create/read round-trip
    - **Property 1: Entity create/read round-trip with defaults**
    - **Validates: Requirements 1.5, 1.6**
  - [x] 2.5 Write property test for Entity required-field/length validation
    - **Property 2: Entity required-field and length validation**
    - **Validates: Requirements 1.2**
  - [x] 2.6 Write property test for Entity uniqueness
    - **Property 3: Entity name/company-code uniqueness is trimmed and case-insensitive**
    - **Validates: Requirements 1.3, 1.4**
  - [x] 2.7 Write property test for Entity partial update
    - **Property 4: Partial update preserves unsupplied fields**
    - **Validates: Requirements 1.8**
  - [x] 2.8 Write property test for not-found on unknown identifiers (cross-master)
    - **Property 5: Not-found for unknown identifiers** (applies to Entity, Vendor, Customer, Product Master, Product Detail, Agreement, Mapping, Invoice)
    - **Validates: Requirements 1.7, 6.10, 7.1, 8.10, 9.6, 10.8, 11.11, 13.6, 14.9, 17.4**
  - [x] 2.9 Write property test for pagination slice + total (cross-master)
    - **Property 6: Pagination returns the requested slice with full total** (applies to every paginated master list)
    - **Validates: Requirements 1.9, 6.11, 8.7, 9.7**
  - [x] 2.10 Write property test for Entity search
    - **Property 7: Search returns all and only matching entities**
    - **Validates: Requirements 1.11**
  - [x] 2.11 Write property test for Entity active-status filter
    - **Property 8: Active-status filter is exact**
    - **Validates: Requirements 1.12**
  - [x] 2.12 Write property test for Entity dropdown membership
    - **Property 9: Dropdown contains exactly the active entities**
    - **Validates: Requirements 2.1**
  - [x] 2.13 Write property test for dropdown label formatting
    - **Property 10: Dropdown label formatting with Unknown substitution**
    - **Validates: Requirements 2.3, 2.4**

- [x] 3. Checkpoint - Entity Master
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. User domain extension (entity link, import, create/edit user)
  - [x] 4.1 Add `entity_id` to User entity and `UserModel`
    - Add nullable `entity_id` FK column on `users` (`ON DELETE SET NULL`) referencing `entities.id`; update the `User` domain entity
    - _Requirements: 3.1_
  - [x] 4.2 Extend UserService with create/edit/import behaviour and schemas
    - Create-user: required/uniqueness for Employee ID + User Name, password ≥ 8 unless AD, validate active Entity + existing roles, store fields, assign/empty roles
    - Edit-user: preserve Employee ID/User Name, validate active Entity, update Email/First/Last/Entity, replace roles, `is_active=false` blocks login, AD toggle, change-password rules
    - Import: resolve Entity by Company Code else Entity Name, create-if-missing, upsert by Employee ID, row-level error + continue for unresolvable rows
    - Add `CreateUserRequest`, `EditUserRequest`, `HrImportRow`, `ImportSummary` schemas
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11_
  - [x] 4.3 Wire create/edit/import endpoints into `user_controller.py`
    - Add/extend routes with permission checks and master-exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 4.4 Write property test for HR import entity resolution
    - **Property 11: HR import resolves and links entities correctly**
    - **Validates: Requirements 3.2, 3.3, 3.4**
  - [x] 4.5 Write property test for import unresolvable rows
    - **Property 12: Import rejects unresolvable rows and continues the batch**
    - **Validates: Requirements 3.5**
  - [x] 4.6 Write property test for import upsert keying
    - **Property 13: Import upsert is keyed by Employee ID**
    - **Validates: Requirements 3.6**
  - [x] 4.7 Write property test for create-user validation
    - **Property 14: Create-user validation**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**
  - [x] 4.8 Write property test for valid user creation
    - **Property 15: Valid user creation stores fields, roles, and entity**
    - **Validates: Requirements 4.7, 4.8, 4.9**
  - [x] 4.9 Write property test for edit-user identity preservation
    - **Property 16: Edit-user preserves identity and validates references**
    - **Validates: Requirements 5.1, 5.3**
  - [x] 4.10 Write property test for valid edit + role replacement
    - **Property 17: Valid edit updates mutable fields and replaces roles**
    - **Validates: Requirements 5.4, 5.5**
  - [x] 4.11 Write property test for deactivation blocking authentication
    - **Property 18: Deactivation blocks authentication**
    - **Validates: Requirements 5.6**
  - [x] 4.12 Write property test for change-password behaviour
    - **Property 19: Change-password behaviour**
    - **Validates: Requirements 5.8, 5.9, 5.10, 5.11**

- [x] 5. Vendor Master
  - [x] 5.1 Implement Vendor domain entity, ORM model, and repository
    - `VendorModel(BaseModel)` per data model table (codes, email, GSTN, bank, `portal_user_id` FK → users.id, `status` default `Active`)
    - `IVendorRepository` + `VendorRepositoryImpl` (uniqueness queries by code/email)
    - _Requirements: 6.1_
  - [x] 5.2 Implement VendorService (CRUD, portal provisioning, deactivation)
    - Validate required/uniqueness/email-format/GSTN; default Status `Active`; provision portal user (`username=vendor_code`, default password) atomically; deactivation sets `Inactive`, blocks portal login + best-effort session invalidation, preserves records
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 7.1, 7.2, 7.3, 7.4, 7.6_
  - [x] 5.3 Implement Vendor schemas and controller
    - Request/response schemas; `vendor_controller.py` with permissions, pagination bounds, deactivate route, exception mapping
    - _Requirements: 6.11, 6.12, 20.2, 20.3_
  - [x] 5.4 Write property test for vendor validation
    - **Property 20: Vendor required-field, format, and uniqueness validation**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6**
  - [x] 5.5 Write property test for valid vendor creation + portal provisioning
    - **Property 21: Valid vendor creation defaults status and provisions portal login**
    - **Validates: Requirements 6.7, 6.8**
  - [x] 5.6 Write property test for vendor deactivation
    - **Property 22: Deactivation sets Inactive and preserves related data**
    - **Validates: Requirements 7.2, 7.6**

- [x] 6. Customer Master
  - [x] 6.1 Implement Customer domain entity, ORM model, and repository
    - `CustomerModel(BaseModel)` per data model table; `ICustomerRepository` + impl with reference-existence checks for delete
    - _Requirements: 8.1_
  - [x] 6.2 Implement CustomerService (CRUD with delete guard)
    - Validate required/uniqueness/type-enum/GSTN/contact lengths/email; default Status `Active`; block delete when referenced by active Mapping or Invoice Header; pagination
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_
  - [x] 6.3 Implement Customer schemas and controller
    - Request/response schemas; `customer_controller.py` with permissions, pagination bounds, exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 6.4 Write property test for customer validation
    - **Property 23: Customer validation rules**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.8, 8.9**
  - [x] 6.5 Write property test for valid customer creation
    - **Property 24: Valid customer creation defaults status Active**
    - **Validates: Requirements 8.5**
  - [x] 6.6 Write property test for customer deletion guard
    - **Property 25: Customer deletion is blocked while referenced**
    - **Validates: Requirements 8.6**

- [x] 7. Product Master and Product Detail
  - [x] 7.1 Implement Product domain entities, ORM models, and repository
    - `ProductMasterModel` and `ProductDetailModel(BaseModel)` (FK `product_master_id` `ON DELETE RESTRICT`); `IProductRepository` + impl
    - _Requirements: 9.1, 10.1_
  - [x] 7.2 Implement ProductService (master + detail CRUD)
    - Master: required/uniqueness, default `Active`, block delete when children exist
    - Detail: required/uniqueness, validate parent master exists, MRP/Rate ≥ 0, GST% 0–100, default `Active`, `product_master_id` filter, resolve product name through hierarchy
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_
  - [x] 7.3 Implement Product schemas and controllers
    - Request/response schemas; `product_master_controller.py` and `product_detail_controller.py` with permissions, pagination bounds, exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 7.4 Write property test for Product Master validation/default
    - **Property 26: Product Master validation and default**
    - **Validates: Requirements 9.2, 9.3, 9.4**
  - [x] 7.5 Write property test for Product Master delete guard
    - **Property 27: Product Master deletion blocked when children exist**
    - **Validates: Requirements 9.5**
  - [x] 7.6 Write property test for Product Detail validation/default
    - **Property 28: Product Detail validation and default**
    - **Validates: Requirements 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**
  - [x] 7.7 Write property test for Product Detail master filter
    - **Property 29: Product Detail master filter**
    - **Validates: Requirements 10.9**
  - [x] 7.8 Write property test for product-name resolution
    - **Property 30: Product name resolves through the hierarchy**
    - **Validates: Requirements 10.10**

- [x] 8. Checkpoint - Core masters
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Commission Calculator (pure domain service)
  - [x] 9.1 Implement commission slab calculator and delay-days computation
    - Pure function in `src/domain/services/commission_calculator.py`: delay ≤ 0 → Max%; delay > 0 → `max(Max% − ceil(delay ÷ slab) × Reduction%, Min%)`; Delay Days = Clearing − Due
    - _Requirements: 12.1, 12.2, 12.3_
  - [x] 9.2 Write property test for commission slab calculation
    - **Property 35: Commission slab calculation is correct and bounded**
    - **Validates: Requirements 12.1, 12.2**
  - [x] 9.3 Write property test for delay-days computation
    - **Property 36: Delay Days equals the day difference**
    - **Validates: Requirements 12.3**

- [x] 10. Agreement Master
  - [x] 10.1 Implement Agreement domain entity, ORM model, and repository
    - `AgreementModel(BaseModel)` per data model table (FKs to vendor/product_detail, `prior_agreement_id` `ON DELETE SET NULL`, index on `(vendor_id, product_detail_id, status)`); `IAgreementRepository` + impl with overlap query
    - _Requirements: 11.1_
  - [x] 10.2 Implement AgreementService (CRUD, overlap, renewal, vendor scoping)
    - Validate vendor/detail existence, From ≤ To, Min ≤ Max, percentages 0–100, Slab > 0, Credit Days ≥ 0, document type/size; apply `Original`/`Active` defaults before validation; inclusive overlap rejection per vendor+detail; renewal marks prior `Renewed` and creates `Renewal` linked atomically; null prior ref on delete; vendor-scoped listing; uses Commission_Calculator
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.11, 13.1, 13.2, 13.3, 13.6, 20.4_
  - [x] 10.3 Implement Agreement schemas and controller
    - Request/response schemas (multipart for document); `agreement_controller.py` with permissions, `vendor_id` filter, renew route, pagination bounds, exception mapping
    - _Requirements: 11.10, 20.2, 20.3, 20.4_
  - [x] 10.4 Implement daily Agreement expiry Celery task
    - Add idempotent task to `schedulers/periodic_tasks.py` calling `expire_due_agreements(today)` inside a transaction with system audit actor
    - _Requirements: 13.4_
  - [x] 10.5 Write property test for agreement field validation
    - **Property 31: Agreement field validation**
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.6, 11.9**
  - [x] 10.6 Write property test for agreement defaults
    - **Property 32: Agreement defaults applied before validation**
    - **Validates: Requirements 11.8**
  - [x] 10.7 Write property test for agreement overlap rule
    - **Property 33: No overlapping active agreements per vendor + product detail**
    - **Validates: Requirements 11.7**
  - [x] 10.8 Write property test for vendor-scoped agreement listing
    - **Property 34: Agreement vendor-scoped listing**
    - **Validates: Requirements 11.10, 20.4**
  - [x] 10.9 Write property test for agreement renewal
    - **Property 37: Renewal marks prior and links new agreement**
    - **Validates: Requirements 13.1, 13.2**
  - [x] 10.10 Write property test for prior-agreement deletion null-ref
    - **Property 38: Deleting a prior agreement nulls renewal references**
    - **Validates: Requirements 13.3**
  - [x] 10.11 Write property test for daily agreement expiry job
    - **Property 39: Daily job expires only past-due active agreements**
    - **Validates: Requirements 13.4**

- [x] 11. Vendor–Customer Mapping
  - [x] 11.1 Implement Mapping domain entity, ORM model, and repository
    - `MappingModel(BaseModel)` per data model table (index on `(vendor_id, customer_id, status)`); `IMappingRepository` + impl with overlap and combined-filter queries
    - _Requirements: 14.1_
  - [x] 11.2 Implement MappingService (CRUD, overlap, filter, dates-only update)
    - Validate vendor/customer existence and From ≤ To; inclusive overlap rejection per vendor+customer; default `Active`; update changes only validity dates; combined vendor/customer filters; vendor-scoped listing; empty-list result
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 20.4_
  - [x] 11.3 Implement Mapping schemas and controller
    - Request/response schemas; `mapping_controller.py` with permissions, `vendor_id`/`customer_id` filters, pagination bounds, exception mapping
    - _Requirements: 20.2, 20.3, 20.4_
  - [x] 11.4 Implement end-of-day Mapping expiry Celery task
    - Add idempotent task calling `expire_due_mappings(today)` inside a transaction; leave on-or-after-date mappings unchanged; retry on failure
    - _Requirements: 15.1, 15.2, 15.3_
  - [x] 11.5 Write property test for mapping validation/default
    - **Property 40: Mapping validation and default**
    - **Validates: Requirements 14.2, 14.3, 14.5**
  - [x] 11.6 Write property test for mapping overlap rule
    - **Property 41: No overlapping active mappings per vendor + customer**
    - **Validates: Requirements 14.4**
  - [x] 11.7 Write property test for mapping dates-only update
    - **Property 42: Mapping update changes only validity dates**
    - **Validates: Requirements 14.6**
  - [x] 11.8 Write property test for mapping filtering
    - **Property 43: Mapping filtering by vendor and/or customer**
    - **Validates: Requirements 14.7**
  - [x] 11.9 Write property test for end-of-day mapping expiry job
    - **Property 44: End-of-day job expires only past-due active mappings**
    - **Validates: Requirements 15.1, 15.2**

- [x] 12. Invoice Master (Header and Line)
  - [x] 12.1 Implement Invoice domain entities, ORM models, and repository
    - `InvoiceHeaderModel` and `InvoiceLineModel(BaseModel)` (FK `invoice_header_id` `ON DELETE CASCADE`); `IInvoiceRepository` + impl (unique invoice number, existence checks)
    - _Requirements: 16.1_
  - [x] 12.2 Implement InvoiceService (atomic create, due-date, status lifecycle)
    - Atomic header+lines; unique Invoice Number; validate vendor/customer/product-detail existence before persist; defaults Amount Deducted 0 / TDS 0 / Status `Open`; due-date supplied vs computed (Invoice Date + Credit Days) vs unset; cascade delete; SAP payment → `Payment Cleared`; final approval → `Settled`; not-found on unknown
    - _Requirements: 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 17.1, 17.2, 17.4_
  - [x] 12.3 Implement Invoice schemas and controller
    - Request/response schemas; `invoice_controller.py` with permissions, SAP-payment and mark-settled routes, exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 12.4 Write property test for invoice creation atomicity/validation
    - **Property 45: Invoice creation is atomic and validated**
    - **Validates: Requirements 16.2, 16.3, 16.4**
  - [x] 12.5 Write property test for invoice defaults + due-date computation
    - **Property 46: Valid invoice creation defaults and due-date computation**
    - **Validates: Requirements 16.5, 16.6, 16.7**
  - [x] 12.6 Write property test for invoice line cascade delete
    - **Property 47: Deleting an invoice header removes its lines**
    - **Validates: Requirements 16.9**
  - [x] 12.7 Write property test for invoice status transitions
    - **Property 48: Invoice status transitions**
    - **Validates: Requirements 17.1, 17.2**

- [x] 13. Claim Validation Triangle
  - [x] 13.1 Implement ClaimValidationService
    - Per-line evaluation of all three checks (active agreement covering date, active mapping covering date, header `Payment Cleared`); allow only when all pass; one distinct error per failed check; surface vendor-inactive, agreement-expired, invoice-settled codes; per-line independence
    - _Requirements: 7.5, 13.5, 17.3, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_
  - [x] 13.2 Implement claim-validation schemas and controller
    - `LineValidationResult`/`LineValidationError` response schemas; `claim_validation_controller.py` with permissions and exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 13.3 Write property test for triangle line eligibility
    - **Property 49: Claim Validation Triangle decides line eligibility**
    - **Validates: Requirements 7.5, 13.5, 17.3, 18.1, 18.2, 18.3, 18.4**
  - [x] 13.4 Write property test for per-line independence
    - **Property 50: Claim validation is per-line independent**
    - **Validates: Requirements 18.5**
  - [x] 13.5 Write property test for one-error-per-failed-check
    - **Property 51: Each failed check yields one distinct error**
    - **Validates: Requirements 18.6**

- [x] 14. Bulk Upload
  - [x] 14.1 Implement BulkUploadService
    - Reject unparseable file (store nothing); process each row independently in a savepoint; resolve Business Codes to UUIDs; skip invalid/unresolvable rows with positional error; return received/stored/skipped + errors with `received == stored + skipped`; delegate per-row to master services
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6_
  - [x] 14.2 Implement bulk-upload schemas and controller
    - `BulkUploadReport`/`BulkRowError` schemas; `bulk_upload_controller.py` with multipart upload, `entity_type` routing, permissions, exception mapping
    - _Requirements: 20.2, 20.3_
  - [x] 14.3 Write property test for bulk row accounting/independence
    - **Property 52: Bulk upload row accounting and independence**
    - **Validates: Requirements 19.1, 19.3, 19.4, 19.5, 19.6**
  - [x] 14.4 Write property test for unparseable file rejection
    - **Property 53: Unparseable bulk file stores nothing**
    - **Validates: Requirements 19.2**

- [x] 15. Migration, wiring, and cross-cutting tests
  - [x] 15.1 Create Alembic migration for all master tables
    - Add a versioned migration creating all master tables, FKs with specified `ON DELETE` rules, unique/ci indexes, and the `users.entity_id` column
    - _Requirements: 1.1, 3.1, 6.1, 8.1, 9.1, 10.1, 11.1, 16.1_
  - [x] 15.2 Register controllers and scheduler jobs
    - Aggregate all master controllers into `api_v1_router` (`src/api/v1/router.py`); register the Agreement daily and Mapping end-of-day tasks in the Celery beat schedule
    - _Requirements: 13.4, 15.1, 20.2, 20.3_
  - [x] 15.3 Write integration tests for audit and session invalidation
    - Audit-log row with old/new values written by `before_flush` on master CRUD (20.1); vendor portal-session invalidation blocks login within time budget (7.3)
    - _Requirements: 20.1, 7.3_
  - [x] 15.4 Write unit/edge-case tests for non-property criteria
    - Out-of-range pagination rejected at boundary (1.10, 6.12); empty dropdown (2.2); no-roles user (4.10); empty mapping list (14.8); unset due date with no agreement (16.8); pre-commit deactivated user still authenticates (5.7); deactivation completes when invalidation throws (7.4); scheduler retry leaves data unchanged (15.3); missing token → 401 (20.2); insufficient permission → 403 (20.3)
    - _Requirements: 1.10, 2.2, 4.10, 5.7, 6.12, 7.4, 14.8, 15.3, 16.8, 20.2, 20.3_
  - [x] 15.5 Write smoke and migration tests
    - Each new model creates its table with UUID PK + audit columns and round-trips; `users.entity_id` exists and is nullable; Alembic upgrade/downgrade applies cleanly
    - _Requirements: 1.1, 3.1, 6.1, 8.1, 9.1, 10.1, 11.1, 16.1_

- [x] 16. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each property test is implemented as a single Hypothesis test in its own module (`@settings(max_examples=100)`), tagged `# Feature: lacm-masters, Property {n}: ...`, so the 53 property tests remain independent and parallelisable.
- Properties 5 (not-found) and 6 (pagination) are cross-master; they are written once (under Entity) and exercise every applicable master, per the design's traceability table.
- Audit logging (20.1) and authentication/authorisation (20.2, 20.3) are satisfied by reused infrastructure; controllers apply `get_current_active_user` and `require_api_permission(...)`, and `BaseModel` + the `before_flush` listener record audit entries automatically.
- Checkpoints provide incremental validation breaks; run the suite and confirm before proceeding.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "4.1", "5.1", "6.1", "7.1", "9.1", "10.1", "11.1", "12.1"] },
    { "id": 2, "tasks": ["2.2", "4.2", "5.2", "6.2", "7.2", "9.2", "9.3", "10.2", "11.2", "12.2", "13.1", "15.1"] },
    { "id": 3, "tasks": ["2.3", "4.3", "5.3", "6.3", "7.3", "10.3", "10.4", "11.3", "11.4", "12.3", "13.2", "14.1"] },
    { "id": 4, "tasks": ["2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "4.12", "5.4", "5.5", "5.6", "6.4", "6.5", "6.6", "7.4", "7.5", "7.6", "7.7", "7.8", "10.5", "10.6", "10.7", "10.8", "10.9", "10.10", "10.11", "11.5", "11.6", "11.7", "11.8", "11.9", "12.4", "12.5", "12.6", "12.7", "13.3", "13.4", "13.5", "14.2"] },
    { "id": 5, "tasks": ["14.3", "14.4", "15.2", "15.3", "15.4", "15.5"] }
  ]
}
```
