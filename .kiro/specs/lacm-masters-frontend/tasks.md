# Implementation Plan: LACM Masters Frontend

## Overview

This plan implements the LACM Masters Frontend module — a React 19 feature module under `src/features/masters/` that provides CRUD management for Entity, Vendor, Customer, Product Master, Product Detail, Agreement, Vendor–Customer Mapping, and Invoice masters. The module uses PrimeReact DataTable, TanStack React Query, Redux Toolkit (RBAC), React Hook Form + Zod, and follows feature-based architecture (api/, components/, hooks/, models/, pages/, routes/, schemas/).

## Tasks

- [x] 1. Set up feature module structure, common types, and routing
  - [x] 1.1 Create feature directory structure and common model types
    - Create `src/features/masters/` directory with subdirectories: api/, components/, hooks/, models/, pages/, routes/, schemas/
    - Create `models/common.ts` with `PaginatedParams`, `PaginatedResponse<T>`, `DropdownOption`, and `BulkUploadResponse` interfaces
    - Create `src/features/masters/index.ts` barrel export
    - _Requirements: 1.1, 14.1, 14.2_

  - [x] 1.2 Create routing configuration and sidebar navigation integration
    - Create `routes/mastersRoutes.tsx` defining routes for all 8 master entities under `/masters/` prefix
    - Each route wrapped with `PrivateRoute` and corresponding `menuKey` (entities, vendors, customers, products, product_details, agreements, mappings, invoices)
    - Add "Masters" group to `APP_NAV_ITEMS` in `MainLayout.tsx` with children for each entity, each gated by `MenuGate` with the appropriate `menuKey`
    - Register master routes in `AppRouter.tsx` under `/masters` parent route
    - Ensure active sidebar item is visually highlighted on navigation
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 13.1, 13.6_

- [x] 2. Implement Entity Master
  - [x] 2.1 Create Entity model, API, hook, and schema
    - Create `models/entity.ts` with `Entity`, `EntityListResponse`, `CreateEntityRequest`, `UpdateEntityRequest`, and `EntityDropdownItem` interfaces
    - Create `api/entityApi.ts` with list, getById, create, update methods
    - Create `hooks/useEntities.ts` with `useEntities`, `useCreateEntity`, `useUpdateEntity` hooks (30s staleTime, invalidateQueries on mutation)
    - Create `schemas/entitySchema.ts` with Zod schema: entity_name non-empty max 255, short_code optional max 50, company_code optional max 50
    - _Requirements: 2.1, 2.5, 14.3, 14.4_

  - [x] 2.2 Write property test for Entity schema validation
    - **Property 2: Entity schema validation — required and length constraints**
    - Use fast-check to generate random string inputs and verify Zod schema accepts iff entity_name is non-empty and ≤255 chars, short_code (if provided) ≤50 chars, company_code (if provided) ≤50 chars
    - Create test at `__tests__/schemas/entitySchema.property.test.ts`
    - **Validates: Requirements 2.5**

  - [x] 2.3 Create EntityFormDialog and EntityListPage
    - Create `components/EntityFormDialog.tsx` — create/edit dialog with fields: Entity Name (required), Short Code (optional), Company Code (optional); pre-populates on edit mode
    - Create `pages/EntityListPage.tsx` — paginated DataTable with columns: Entity Name, Short Code, Company Code, Status (Active/Inactive tag), Actions
    - Implement column-level case-insensitive search filtering on Entity Name, Short Code, Company Code
    - Implement "Active Only" toggle filter (defaults to showing all records)
    - Implement entity dropdown formatter: "{Short Code} - {Entity Name}" with "Unknown" substitution for empty short_code
    - Handle 409 conflict (Toast_Notification), 422 validation (inline errors), success (Toast + close dialog + refresh)
    - Wrap action buttons with `PermissionGate`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 12.1, 12.4, 12.5, 12.6, 12.7, 13.2, 14.5, 14.6, 16.2, 16.4_

  - [x] 2.4 Write property test for Entity dropdown formatting
    - **Property 1: Entity dropdown formatting**
    - Use fast-check to generate Entity objects with arbitrary short_code (null, empty, or valid string) and entity_name, verify formatter produces correct pattern
    - Create test at `__tests__/schemas/entitySchema.property.test.ts` (or separate file)
    - **Validates: Requirements 2.9, 10.10**

- [x] 3. Implement Vendor Master
  - [x] 3.1 Create Vendor model, API, hook, and schema
    - Create `models/vendor.ts` with `Vendor`, `VendorListResponse`, `CreateVendorRequest`, `UpdateVendorRequest` types
    - Create `api/vendorApi.ts` with list, getById, create, update, deactivate methods
    - Create `hooks/useVendors.ts` with `useVendors`, `useCreateVendor`, `useUpdateVendor`, `useDeactivateVendor` hooks
    - Create `schemas/vendorSchema.ts` with Zod schema: vendor_code (non-empty, max 50), vendor_name (non-empty, max 200), vendor_email (non-empty, valid email, max 254), gstn_number (optional, regex `[A-Z0-9]{15}`), pan_number (max 10), bank_account_no (max 30), bank_ifsc (max 11), bank_name (max 100), vendor_contact (max 20)
    - _Requirements: 3.1, 3.4, 14.3, 14.4_

  - [x] 3.2 Write property test for Vendor schema validation
    - **Property 3: Vendor schema validation — patterns and format constraints**
    - Use fast-check to generate random vendor form data and verify Zod schema acceptance/rejection matches defined constraints
    - Create test at `__tests__/schemas/vendorSchema.property.test.ts`
    - **Validates: Requirements 3.4**

  - [x] 3.3 Create VendorFormDialog, VendorDeactivateDialog, and VendorListPage
    - Create `components/VendorFormDialog.tsx` — create/edit dialog with all vendor fields; pre-populates on edit mode
    - Create `components/VendorDeactivateDialog.tsx` — confirmation dialog warning that deactivation blocks portal access
    - Create `pages/VendorListPage.tsx` — paginated DataTable with columns: Vendor Code, Vendor Name, Vendor Email, Contact, GSTN Number, Status, Actions
    - Implement column-level search filtering on Vendor Code, Vendor Name, Vendor Email
    - Handle vendor creation success Toast (portal login provisioned), 409 conflict, 422 validation, deactivation flow
    - Wrap edit action with PermissionGate for vendor update permission
    - Wrap deactivate action with PermissionGate for vendor deactivate permission
    - Wrap bulk upload button with PermissionGate
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 12.1, 12.5, 12.7, 13.2, 13.3, 13.4_

- [x] 4. Implement Customer Master
  - [x] 4.1 Create Customer model, API, hook, and schema
    - Create `models/customer.ts` with `Customer`, `CustomerListResponse`, `CreateCustomerRequest`, `UpdateCustomerRequest` types
    - Create `api/customerApi.ts` with list, getById, create, update, delete methods
    - Create `hooks/useCustomers.ts` with `useCustomers`, `useCreateCustomer`, `useUpdateCustomer`, `useDeleteCustomer` hooks
    - Create `schemas/customerSchema.ts` with Zod schema: customer_code (non-empty, max 50), customer_name (non-empty, max 255), customer_type (enum dropdown), gstn_number (optional, regex `[A-Z0-9]{15}`), contact_email (optional, valid email, max 255), contact_number (optional, max 20), contact_person (optional, max 100)
    - _Requirements: 4.1, 4.4, 14.3, 14.4_

  - [x] 4.2 Write property test for Customer schema validation
    - **Property 4: Customer schema validation — code, GSTN, and email constraints**
    - Use fast-check to generate random customer form data and verify Zod schema acceptance/rejection
    - Create test at `__tests__/schemas/customerSchema.property.test.ts`
    - **Validates: Requirements 4.4**

  - [x] 4.3 Create CustomerFormDialog and CustomerListPage
    - Create `components/CustomerFormDialog.tsx` — create/edit dialog with Customer Type dropdown (Government Medical Corporation, Hospital, Pharmacy, Institution, Other)
    - Create `pages/CustomerListPage.tsx` — paginated DataTable with columns: Customer Code, Customer Name, Customer Type, Contact Person, Contact Email, Status, Actions
    - Implement column-level search filtering on Customer Code, Customer Name, Customer Type
    - Handle 409 conflict, delete-guard error Toast, 422 validation, success flow
    - Integrate Bulk_Upload_Dialog with entity_type "customer"
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 12.1, 12.5, 13.2, 13.3_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Product Master and Product Detail
  - [x] 6.1 Create Product Master model, API, hook, and schema
    - Create `models/productMaster.ts` with `ProductMaster`, `ProductMasterListResponse`, `CreateProductMasterRequest`, `UpdateProductMasterRequest` types
    - Create `api/productMasterApi.ts` with list, getById, create, update methods
    - Create `hooks/useProductMasters.ts` with `useProductMasters`, `useCreateProductMaster`, `useUpdateProductMaster` hooks
    - Create `schemas/productMasterSchema.ts` with Zod schema: basic_material_code (non-empty, max 50), product_name (non-empty, max 255), therapeutic_category (optional)
    - _Requirements: 5.1, 5.4, 14.3, 14.4_

  - [x] 6.2 Create ProductMasterFormDialog and ProductMasterListPage
    - Create `components/ProductMasterFormDialog.tsx` — create/edit dialog
    - Create `pages/ProductMasterListPage.tsx` — paginated DataTable with columns: Basic Material Code, Product Name, Therapeutic Category, Status, Actions
    - Implement column-level search filtering on Basic Material Code, Product Name, Therapeutic Category
    - Handle 409 conflict, delete-guard error Toast, bulk upload integration with entity_type "product_master"
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9, 12.1, 12.5, 13.2_

  - [x] 6.3 Create Product Detail model, API, hook, and schema
    - Create `models/productDetail.ts` with `ProductDetail`, `ProductDetailListResponse`, `CreateProductDetailRequest`, `UpdateProductDetailRequest` types
    - Create `api/productDetailApi.ts` with list, getById, create, update methods
    - Create `hooks/useProductDetails.ts` with `useProductDetails`, `useCreateProductDetail`, `useUpdateProductDetail` hooks
    - Create `schemas/productDetailSchema.ts` with Zod schema: child_code (non-empty, max 50), product_master_id (required), variant_description (max 200), hsn_code (max 20), pack_size (max 50), unit_of_measure (max 20), MRP (0–999999999.99), Rate (0–999999999.99), GST % (0–100)
    - _Requirements: 6.1, 6.5, 14.3, 14.4_

  - [x] 6.4 Write property test for Product Detail schema validation
    - **Property 5: Product Detail schema validation — numeric range constraints**
    - Use fast-check to generate numeric inputs and verify Zod schema acceptance for MRP, Rate, GST% ranges
    - Create test at `__tests__/schemas/productDetailSchema.property.test.ts`
    - **Validates: Requirements 6.5**

  - [x] 6.5 Create ProductDetailFormDialog and ProductDetailListPage
    - Create `components/ProductDetailFormDialog.tsx` — create/edit dialog with Product Master dropdown (active only), Child Code read-only on edit
    - Create `pages/ProductDetailListPage.tsx` — paginated DataTable with columns: Child Code, Product Master, Variant Description, HSN Code, Pack Size, UoM, MRP, Rate, GST %, Status, Actions
    - Implement Product Master dropdown filter and column-level search on Child Code, Variant Description
    - Handle 409 conflict, bulk upload with entity_type "product_detail"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 6.8, 6.9, 12.1, 12.5, 13.2_

- [x] 7. Implement Agreement Master
  - [x] 7.1 Create Agreement model, API, hook, and schema
    - Create `models/agreement.ts` with `Agreement`, `AgreementListResponse`, `CreateAgreementRequest`, `UpdateAgreementRequest`, `RenewAgreementRequest` types
    - Create `api/agreementApi.ts` with list, getById, create, update, renew methods (renew endpoint)
    - Create `hooks/useAgreements.ts` with `useAgreements`, `useCreateAgreement`, `useUpdateAgreement`, `useRenewAgreement` hooks; include vendor_id filter from Redux auth state for vendor agent role
    - Create `schemas/agreementSchema.ts` with Zod schema: from_date ≤ to_date, min_commission ≤ max_commission, slab_in_days integer > 0, reduction_percent 0–100, max/min commission 0–100, credit_days integer ≥ 0, agreement_document (optional, PDF/JPEG/PNG, max 10 MB)
    - _Requirements: 7.1, 7.2, 7.5, 1.5, 14.3, 14.4_

  - [x] 7.2 Write property test for Agreement schema validation
    - **Property 6: Agreement schema validation — cross-field date and commission constraints**
    - Use fast-check to generate date pairs, commission percentages, slab values and verify Zod schema cross-field validation
    - Create test at `__tests__/schemas/agreementSchema.property.test.ts`
    - **Validates: Requirements 7.5**

  - [x] 7.3 Create AgreementFormDialog, AgreementRenewalDialog, CommissionSlabInfo, and AgreementListPage
    - Create `components/AgreementFormDialog.tsx` — create/edit dialog with Vendor dropdown, Product Detail dropdown, date pickers, numeric slab fields, file upload
    - Create `components/AgreementRenewalDialog.tsx` — renewal dialog with vendor/product read-only, new date/slab fields
    - Create `components/CommissionSlabInfo.tsx` — read-only panel showing commission slab formula
    - Create `pages/AgreementListPage.tsx` — paginated DataTable with columns: Vendor Name, Product Detail, From Date, To Date, Max Commission %, Min Commission %, Credit Days, Agreement Type tag, Status tag, Actions
    - Implement vendor agent role filtering (auto-apply vendor_id from Redux auth state)
    - Implement column-level search on Vendor Name and Product Detail
    - Handle 409 overlap conflict Toast, renewal flow (prior marked Renewed, new Renewal-type created), bulk upload with entity_type "agreement"
    - Show "Renew" action only on Active agreements
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 1.5, 12.1, 12.5, 13.2_

- [x] 8. Implement Vendor–Customer Mapping
  - [x] 8.1 Create Mapping model, API, hook, and schema
    - Create `models/mapping.ts` with `VendorCustomerMapping`, `MappingListResponse`, `CreateMappingRequest`, `UpdateMappingRequest` types
    - Create `api/mappingApi.ts` with list, getById, create, update, delete methods
    - Create `hooks/useMappings.ts` with `useMappings`, `useCreateMapping`, `useUpdateMapping`, `useDeleteMapping` hooks; include vendor_id filter for vendor agent role
    - Create `schemas/mappingSchema.ts` with Zod schema: validity_from ≤ validity_to date constraint
    - _Requirements: 8.1, 8.2, 8.5, 1.5, 14.3, 14.4_

  - [x] 8.2 Write property test for Mapping schema validation
    - **Property 7: Mapping schema validation — date ordering constraint**
    - Use fast-check to generate date pairs and verify Zod schema accepts iff validity_from ≤ validity_to
    - Create test at `__tests__/schemas/mappingSchema.property.test.ts`
    - **Validates: Requirements 8.5**

  - [x] 8.3 Create MappingFormDialog and MappingListPage
    - Create `components/MappingFormDialog.tsx` — create dialog with Vendor and Customer dropdowns + date pickers; edit mode shows Vendor/Customer read-only, only dates editable
    - Create `pages/MappingListPage.tsx` — paginated DataTable with columns: Vendor Name, Customer Name, Validity From, Validity To, Status tag, Actions
    - Implement dropdown filters for Vendor and Customer
    - Implement vendor agent role filtering (auto-apply vendor_id from Redux auth state)
    - Handle 409 overlap conflict Toast, delete confirmation dialog, delete-guard error Toast, bulk upload with entity_type "mapping"
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 1.5, 12.1, 12.5, 13.2, 13.3_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Invoice Master
  - [x] 10.1 Create Invoice model, API, hook, and schema
    - Create `models/invoice.ts` with `Invoice`, `InvoiceLine`, `InvoiceListResponse`, `CreateInvoiceRequest`, `CreateInvoiceLineRequest`, `PaymentUpdateRequest`, `EligibilityCheck` types
    - Create `api/invoiceApi.ts` with list, getById, create, updatePayment, markSettled, checkEligibility methods
    - Create `hooks/useInvoices.ts` with `useInvoices`, `useCreateInvoice`, `useUpdatePayment`, `useMarkSettled`, `useCheckEligibility` hooks
    - Create `schemas/invoiceSchema.ts` with Zod schema: invoice_number (non-empty), invoice_date (required), vendor_id (required), customer_id (required), bill_amount_excl_gst (positive number), lines (min 1 item with product_detail_id required)
    - _Requirements: 9.1, 9.5, 14.3, 14.4_

  - [x] 10.2 Write property test for Invoice schema validation
    - **Property 8: Invoice schema validation — positive amounts and non-empty lines**
    - Use fast-check to generate invoice form data and verify Zod schema acceptance/rejection for amount positivity and non-empty lines constraints
    - Create test at `__tests__/schemas/invoiceSchema.property.test.ts`
    - **Validates: Requirements 9.5**

  - [x] 10.3 Create InvoiceForm, InvoiceLineItems, PaymentUpdateDialog, SettleConfirmDialog, EligibilityPanel, and InvoiceListPage
    - Create `components/InvoiceForm.tsx` — creation form with header fields and dynamic line items section
    - Create `components/InvoiceLineItems.tsx` — dynamic add/edit/remove line items with Product Detail dropdown, Quantity, Line Amount, VAT/GST Amount
    - Create `components/PaymentUpdateDialog.tsx` — dialog with Payment Clearing Date and SAP Clearing Document No
    - Create `components/SettleConfirmDialog.tsx` — confirmation dialog for marking invoice as Settled
    - Create `components/EligibilityPanel.tsx` — read-only panel showing 3-check claim validation triangle with pass/fail indicators
    - Create `pages/InvoiceListPage.tsx` — paginated DataTable with columns: Invoice Number, Invoice Date, Vendor Name, Customer Name, Bill Amount, Due Date, Payment Clearing Date, Invoice Status tag, Actions
    - Implement column-level search on Invoice Number, Vendor Name, Customer Name
    - Display auto-calculated Due Date as read-only after creation
    - Disable "Update Payment" for non-Open invoices, disable "Mark Settled" for non-Payment Cleared invoices
    - Handle 409 duplicate invoice number, payment update flow, settle flow, eligibility check
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 12.1, 12.5, 13.2, 15.1, 15.2, 15.3, 15.4_

- [x] 11. Implement Bulk Upload Dialog (shared component)
  - [x] 11.1 Create BulkUploadDialog shared component and bulkUploadApi
    - Create `api/bulkUploadApi.ts` with upload method accepting file + entity_type, and template download URL helper
    - Create `components/BulkUploadDialog.tsx` with props: visible, onHide, entityType, onSuccess
    - Implement: file input (CSV/XLSX), file name/size display, upload to `/bulk-upload` with entity_type, progress spinner, disable button during upload
    - Display results summary (total, successful, failed), scrollable error table for row-level errors
    - Handle malformed file error (Toast without results panel)
    - Provide "Download Template" link per entity type
    - On close after success, trigger parent table refresh via onSuccess callback
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10_

- [x] 12. Implement User Create/Edit page updates
  - [x] 12.1 Update Create User and Edit User pages with Entity dropdown and AD toggle
    - Update Create User page: add Entity dropdown (active entities, formatted as "{Short Code} - {Entity Name}"), add "Validate with AD" toggle (default false)
    - Implement conditional password field: hide/disable Password when AD toggle is enabled, enforce min 8 chars when disabled
    - Update Edit User page: add Entity dropdown, add "Validate with AD" toggle, add "Change Password" field (optional, hidden when AD enabled, min 8 chars if provided)
    - Implement "Is Active" toggle with confirmation warning on deactivation
    - Update user form Zod schemas for conditional password validation
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - [x] 12.2 Write property test for User create form conditional password validation
    - **Property 9: User create form — conditional password validation**
    - Use fast-check to generate form data with varying is_validate_ad and password values, verify Zod schema conditional requirement
    - Create test at `__tests__/schemas/userSchema.property.test.ts`
    - **Validates: Requirements 10.4**

- [x] 13. Implement shared error handling utilities and accessibility
  - [x] 13.1 Create error mapping utility and integrate global error handling
    - Create utility function `mapBackendErrors` to map 422 response detail array to react-hook-form field errors via `setError()`
    - Ensure all form dialogs use this utility for 422 responses
    - Ensure all pages handle 400/409 with Toast (severity "error"), 500 with generic Toast
    - Ensure submit buttons are disabled with spinner during submission across all forms
    - Add aria-label attributes to all DataTable components and form controls
    - Ensure dialogs are keyboard-navigable (Tab, Shift+Tab, Escape to close)
    - Add tooltip descriptions and accessible labels to all action buttons
    - Use PrimeReact Tag with severity styling for all status displays
    - Ensure responsive layout with PrimeReact grid classes (adapt to 768px viewports)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 13.5, 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design (9 properties using fast-check)
- Unit tests validate specific examples and edge cases
- All code is TypeScript with React 19, PrimeReact, TanStack React Query, Redux Toolkit, React Hook Form + Zod
- The BulkUploadDialog (task 11) is referenced by Vendor, Customer, Product Master, Product Detail, Agreement, and Mapping pages — it can be implemented in parallel with earlier page tasks as long as it's wired in after creation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "3.1", "4.1", "6.1", "11.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.3", "4.2", "4.3", "6.2", "6.3"] },
    { "id": 4, "tasks": ["2.4", "6.4", "6.5", "7.1", "8.1", "10.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.2", "8.3", "10.2", "10.3"] },
    { "id": 6, "tasks": ["12.1"] },
    { "id": 7, "tasks": ["12.2", "13.1"] }
  ]
}
```
