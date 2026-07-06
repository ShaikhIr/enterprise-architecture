# Requirements Document

## Introduction

This document defines the frontend requirements for the LACM Masters module — the UI layer for managing Entity, Vendor, Customer, Product, Agreement, Vendor–Customer Mapping, and Invoice masters within the Liaisoning Agent Commission Management (LACM) application. The frontend consumes existing backend REST APIs and follows the established React 19 + PrimeReact + TanStack Query architecture with dynamic RBAC enforcement.

## Glossary

- **Masters_UI**: The collection of frontend pages, forms, dialogs, tables, and navigation elements that provide CRUD and management capabilities for all LACM master entities.
- **Entity_Page**: The list page and create/edit dialog for managing Entity Master records.
- **Vendor_Page**: The list page and create/edit dialog for managing Vendor Master records including deactivation and bulk upload.
- **Customer_Page**: The list page and create/edit dialog for managing Customer Master records including bulk upload.
- **Product_Master_Page**: The list page and create/edit dialog for managing Product Master records including bulk upload.
- **Product_Detail_Page**: The list page and create/edit dialog for managing Product Detail (SKU) records including bulk upload.
- **Agreement_Page**: The list page and create/edit dialog for managing Agreement Master records including renewal and bulk upload.
- **Mapping_Page**: The list page and create/edit dialog for managing Vendor–Customer Mapping records including bulk upload.
- **Invoice_Page**: The list page and creation form for managing Invoice Header and Line records including SAP payment updates.
- **Bulk_Upload_Dialog**: A shared reusable dialog component for uploading CSV/Excel files for any master entity type.
- **DataTable**: The PrimeReact DataTable component used for paginated, sortable, filterable list views.
- **RBAC_Guard**: Frontend permission enforcement components (PrivateRoute, MenuGate, PermissionGate, FieldGate) from the core/rbac module.
- **API_Hook**: A TanStack React Query custom hook that encapsulates server-state fetching and mutation for a specific entity.
- **Form_Schema**: A Zod validation schema defining field constraints for create/edit forms.
- **Toast_Notification**: A PrimeReact Toast component used to display success, error, and warning messages to the user.

## Requirements

### Requirement 1: Navigation and Routing

**User Story:** As an authenticated user, I want to access all master management pages from a dedicated "Masters" section in the sidebar navigation, so that I can quickly navigate to any master module.

#### Acceptance Criteria

1. THE Masters_UI SHALL register routes for each master entity under the `/masters/` path prefix: `/masters/entities`, `/masters/vendors`, `/masters/customers`, `/masters/products`, `/masters/product-details`, `/masters/agreements`, `/masters/mappings`, `/masters/invoices`.
2. THE Masters_UI SHALL display a "Masters" group in the sidebar navigation containing sub-items for each master entity: Entities, Vendors, Customers, Products, Product Details, Agreements, Mappings, and Invoices, where each sub-item is wrapped with MenuGate using the menuKey corresponding to its entity (entities, vendors, customers, products, product_details, agreements, mappings, invoices).
3. WHEN a user navigates to a masters route, THE RBAC_Guard SHALL verify the user has the matching menu permission (menuKey "entities" for `/masters/entities`, "vendors" for `/masters/vendors`, "customers" for `/masters/customers`, "products" for `/masters/products`, "product_details" for `/masters/product-details`, "agreements" for `/masters/agreements`, "mappings" for `/masters/mappings`, "invoices" for `/masters/invoices`) before rendering the page content.
4. IF a user does not have the required menu permission for the requested masters route, THEN THE RBAC_Guard SHALL redirect the user to the `/unauthorized` page.
5. WHILE the logged-in user has the "Vendor Agent" role, THE Agreement_Page SHALL filter the agreements list to show only records belonging to the vendor associated with the logged-in user, and THE Mapping_Page SHALL filter the mappings list to show only records belonging to the vendor associated with the logged-in user.
6. WHEN the user navigates to a masters sub-item route, THE Masters_UI SHALL visually indicate the active sub-item in the sidebar navigation by applying the active style to the corresponding menu entry.

---

### Requirement 2: Entity Master Page

**User Story:** As an administrator, I want to manage legal company entities through a list view with search, filter, and create/edit capabilities, so that I can maintain the organisation structure.

#### Acceptance Criteria

1. THE Entity_Page SHALL display a paginated DataTable showing columns: Entity Name, Short Code, Company Code, Status (Active/Inactive tag), and Actions.
2. THE Entity_Page SHALL support case-insensitive substring search filtering on Entity Name, Short Code, and Company Code columns, applied per-column via filter input fields in the column headers.
3. THE Entity_Page SHALL provide an "Active Only" toggle filter that defaults to showing all records (both Active and Inactive).
4. WHEN the user clicks the "New Entity" button, THE Entity_Page SHALL open a create dialog with fields: Entity Name (required), Short Code (optional), Company Code (optional).
5. WHEN the user submits the create form, THE Form_Schema SHALL validate that Entity Name is non-empty and does not exceed 255 characters, Short Code (if provided) does not exceed 50 characters, and Company Code (if provided) does not exceed 50 characters.
6. WHEN the backend returns a uniqueness conflict (409) for Entity Name or Company Code, THE Entity_Page SHALL display a Toast_Notification with the specific conflict message returned by the backend.
7. WHEN the user clicks the edit action on a row, THE Entity_Page SHALL open an edit dialog pre-populated with the existing entity data (Entity Name, Short Code, Company Code).
8. WHEN the user submits the edit form successfully, THE Entity_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
9. THE Entity_Page SHALL format dropdown options as "{Short Code} - {Entity Name}", substituting "Unknown" for Short Code when the value is empty or not provided.
10. WHEN the user submits the create or edit form and the backend returns a validation error (422), THE Entity_Page SHALL display inline error messages below the corresponding invalid fields.

---

### Requirement 3: Vendor Master Page

**User Story:** As an administrator, I want to manage vendor (liaisoning agent) records with portal provisioning, deactivation, and bulk upload capabilities, so that I can onboard and manage external agents.

#### Acceptance Criteria

1. THE Vendor_Page SHALL display a paginated DataTable showing columns: Vendor Code, Vendor Name, Vendor Email, Contact, GSTN Number, Status (Active/Inactive tag), and Actions.
2. THE Vendor_Page SHALL support column-level search filtering on Vendor Code, Vendor Name, and Vendor Email.
3. WHEN the user clicks the "New Vendor" button, THE Vendor_Page SHALL open a create dialog with fields: Vendor Code (required), Vendor Name (required), Vendor Email (required), Vendor Contact, Vendor Address, GSTN Number, PAN Number, Bank Account No, Bank IFSC, Bank Name.
4. WHEN the user submits the create form, THE Form_Schema SHALL validate: Vendor Code is non-empty and max 50 characters, Vendor Name is non-empty and max 200 characters, Vendor Email is a valid email format and max 254 characters, Vendor Contact max 20 characters, GSTN Number (if provided) matches pattern `[A-Z0-9]{15}`, PAN Number max 10 characters, Bank Account No max 30 characters, Bank IFSC max 11 characters, Bank Name max 100 characters.
5. WHEN a vendor is successfully created, THE Vendor_Page SHALL display a Toast_Notification informing that the vendor and portal login have been provisioned.
6. WHEN the backend returns a uniqueness conflict (409) for Vendor Code or Vendor Email, THE Vendor_Page SHALL display a Toast_Notification with the specific conflict message returned by the backend.
7. WHEN the user clicks the edit action on a vendor row, THE Vendor_Page SHALL open an edit dialog pre-populated with the existing vendor data.
8. WHEN the user submits the edit form successfully, THE Vendor_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
9. WHEN the user clicks the "Deactivate" action on an active vendor row, THE Vendor_Page SHALL display a confirmation dialog warning that deactivation will block portal access and claim submissions.
10. WHEN the user confirms deactivation, THE Vendor_Page SHALL call the deactivate endpoint (not delete), update the row status to Inactive, and display a success Toast_Notification.
11. WHEN the user clicks the "Bulk Upload" button, THE Vendor_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "vendor".
12. THE Vendor_Page SHALL display the edit action only when the user has the vendor update permission via PermissionGate.

---

### Requirement 4: Customer Master Page

**User Story:** As an administrator, I want to manage customer records (government bodies, hospitals, pharmacies, institutions) with bulk upload support, so that I can maintain the customer base for vendor-customer associations.

#### Acceptance Criteria

1. THE Customer_Page SHALL display a paginated DataTable showing columns: Customer Code, Customer Name, Customer Type, Contact Person, Contact Email, Status (Active/Inactive tag), and Actions.
2. THE Customer_Page SHALL support column-level search filtering on Customer Code, Customer Name, and Customer Type.
3. WHEN the user clicks the "New Customer" button, THE Customer_Page SHALL open a create dialog with fields: Customer Code (required), Customer Name (required), Customer Type (dropdown: Government Medical Corporation, Hospital, Pharmacy, Institution, Other), Address, GSTN Number, Contact Person, Contact Number, Contact Email.
4. WHEN the user submits the create form, THE Form_Schema SHALL validate: Customer Code is non-empty and max 50 characters, Customer Name is non-empty and max 255 characters, GSTN Number (if provided) matches pattern `[A-Z0-9]{15}`, Contact Email (if provided) is valid email format and max 255 characters, Contact Number (if provided) max 20 characters, Contact Person (if provided) max 100 characters.
5. WHEN the backend returns a conflict error for duplicate Customer Code (409), THE Customer_Page SHALL display a Toast_Notification with the specific conflict message.
6. WHEN the user clicks the edit action on a row, THE Customer_Page SHALL open an edit dialog pre-populated with the existing customer data.
7. WHEN the user submits the edit form successfully, THE Customer_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
8. WHEN the backend returns a delete-guard error (referenced by active mapping or invoice), THE Customer_Page SHALL display a Toast_Notification explaining that the customer cannot be deleted due to active references.
9. WHEN the user clicks the "Bulk Upload" button, THE Customer_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "customer".

---

### Requirement 5: Product Master Page

**User Story:** As an administrator, I want to manage the base product (molecule/formulation) records with bulk upload support, so that I can maintain the product hierarchy for SKU associations.

#### Acceptance Criteria

1. THE Product_Master_Page SHALL display a paginated DataTable showing columns: Basic Material Code, Product Name, Therapeutic Category, Status (Active/Inactive tag), and Actions.
2. THE Product_Master_Page SHALL support column-level search filtering on Basic Material Code, Product Name, and Therapeutic Category.
3. WHEN the user clicks the "New Product" button, THE Product_Master_Page SHALL open a create dialog with fields: Basic Material Code (required), Product Name (required), Therapeutic Category (optional).
4. WHEN the user submits the create form, THE Form_Schema SHALL validate: Basic Material Code is non-empty and max 50 characters, Product Name is non-empty and max 255 characters.
5. WHEN the backend returns a conflict error for duplicate Basic Material Code (409), THE Product_Master_Page SHALL display a Toast_Notification with the specific conflict message.
6. WHEN the user clicks the edit action on a row, THE Product_Master_Page SHALL open an edit dialog pre-populated with the existing product master data.
7. WHEN the user submits the edit form successfully, THE Product_Master_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
8. WHEN the backend returns a delete-guard error (referenced by active Product Detail children), THE Product_Master_Page SHALL display a Toast_Notification explaining that the product master cannot be deleted due to existing product detail records.
9. WHEN the user clicks the "Bulk Upload" button, THE Product_Master_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "product_master".

---

### Requirement 6: Product Detail Page

**User Story:** As an administrator, I want to manage product detail (SKU/child variant) records with parent product filtering and bulk upload, so that I can maintain billable product variants linked to base products.

#### Acceptance Criteria

1. THE Product_Detail_Page SHALL display a paginated DataTable showing columns: Child Code, Product Master (name from parent), Variant Description, HSN Code, Pack Size, Unit of Measure, MRP, Rate, GST %, Status (Active/Inactive tag), and Actions.
2. THE Product_Detail_Page SHALL provide a dropdown filter to filter records by Product Master (parent), populated with active product masters only.
3. THE Product_Detail_Page SHALL support column-level search filtering on Child Code and Variant Description.
4. WHEN the user clicks the "New Product Detail" button, THE Product_Detail_Page SHALL open a create dialog with fields: Child Code (required, max 50 characters), Product Master (required, dropdown of active product masters), Variant Description (max 200 characters), HSN Code (max 20 characters), Pack Size (max 50 characters), Unit of Measure (max 20 characters), MRP (numeric), Rate (numeric), GST % (numeric).
5. WHEN the user submits the create form, THE Form_Schema SHALL validate: Child Code is non-empty and max 50 characters, Product Master is selected, MRP (if provided) is between 0 and 999,999,999.99, Rate (if provided) is between 0 and 999,999,999.99, GST % (if provided) is between 0 and 100.
6. WHEN the backend returns a conflict error for duplicate Child Code (409), THE Product_Detail_Page SHALL display a Toast_Notification with the specific conflict message.
7. WHEN the user clicks the edit action on a row, THE Product_Detail_Page SHALL open an edit dialog pre-populated with the existing product detail data, with Child Code displayed as read-only.
8. WHEN the user submits the edit form successfully, THE Product_Detail_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
9. WHEN the user clicks the "Bulk Upload" button, THE Product_Detail_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "product_detail".

---

### Requirement 7: Agreement Master Page

**User Story:** As an administrator or vendor agent, I want to manage commission agreement records with slab parameters, date validation, renewal workflow, and bulk upload, so that I can define and maintain vendor entitlements per product.

#### Acceptance Criteria

1. THE Agreement_Page SHALL display a paginated DataTable showing columns: Vendor Name, Product Detail (Child Code + Product Name), From Date, To Date, Max Commission %, Min Commission %, Credit Days, Agreement Type (Original/Renewal tag), Status (Active/Expired/Renewed tag), and Actions.
2. WHILE the logged-in user has the vendor agent role, THE Agreement_Page SHALL filter the list to show only agreements belonging to the vendor associated with the logged-in user.
3. THE Agreement_Page SHALL support column-level search filtering on Vendor Name and Product Detail.
4. WHEN the user clicks the "New Agreement" button, THE Agreement_Page SHALL open a create dialog with fields: Vendor (required, dropdown of active vendors), Product Detail (required, dropdown of active product details), From Date (required, date picker), To Date (required, date picker), Slab in Days (required, numeric, integer), Reduction % (required, numeric), Max Commission % (required, numeric), Min Commission % (required, numeric), Credit Days (required, numeric, integer, default 0), Agreement Document (optional file upload, max 10 MB, PDF/JPEG/PNG).
5. WHEN the user submits the create form, THE Form_Schema SHALL validate: From Date is on or before To Date, Min Commission % is less than or equal to Max Commission %, Slab in Days is an integer greater than 0, Reduction % is between 0 and 100, Max Commission % is between 0 and 100, Min Commission % is between 0 and 100, Credit Days is an integer greater than or equal to 0, Agreement Document (if provided) is PDF/JPEG/PNG and does not exceed 10 MB in size.
6. WHEN the backend returns an overlap conflict error (409), THE Agreement_Page SHALL display a Toast_Notification explaining that an active agreement already exists for the same vendor and product detail within the specified date range.
7. WHEN the user clicks the "Renew" action on an active agreement row, THE Agreement_Page SHALL open a renewal dialog pre-populated with the vendor and product detail (both read-only) from the original agreement, allowing the user to set new From Date, To Date, Slab in Days, Reduction %, Max Commission %, Min Commission %, and Credit Days.
8. WHEN the user submits the renewal form, THE Form_Schema SHALL apply the same validation rules as the create form (criterion 5), and upon success THE Agreement_Page SHALL call the renewal endpoint, and refresh the table to show the prior agreement marked as Renewed and the new Renewal-type agreement.
9. THE Agreement_Page SHALL display the commission slab formula as a read-only information panel within the create and edit dialogs, showing the calculation rule: "Max Commission % reduced by Reduction % for each Slab in Days of payment delay past due date, floored at Min Commission %".
10. WHEN the user clicks the "Bulk Upload" button, THE Agreement_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "agreement".
11. THE Agreement_Page SHALL display the "Renew" action only on agreement rows with Status equal to Active.

---

### Requirement 8: Vendor–Customer Mapping Page

**User Story:** As an administrator or vendor agent, I want to manage vendor-customer mapping records with date-based validity, overlap prevention, and bulk upload, so that I can control which vendors are authorised to service which customers.

#### Acceptance Criteria

1. THE Mapping_Page SHALL display a paginated DataTable showing columns: Vendor Name, Customer Name, Validity From, Validity To, Status (Active/Expired tag derived from the record's status field), and Actions.
2. WHILE the logged-in user has the vendor agent role, THE Mapping_Page SHALL filter the list to show only mappings belonging to the vendor associated with the logged-in user.
3. THE Mapping_Page SHALL support dropdown filters for Vendor and Customer to narrow the list.
4. WHEN the user clicks the "New Mapping" button, THE Mapping_Page SHALL open a create dialog with fields: Vendor (required, dropdown of active vendors), Customer (required, dropdown of active customers), Validity From (required, date picker), Validity To (required, date picker).
5. WHEN the user submits the create form, THE Form_Schema SHALL validate: Validity From is on or before Validity To.
6. WHEN the backend returns an overlap conflict error (409), THE Mapping_Page SHALL display a Toast_Notification explaining that an active mapping already exists for the same vendor and customer combination within the specified date range.
7. WHEN the user clicks the edit action on a row, THE Mapping_Page SHALL open an edit dialog allowing modification of Validity From and Validity To only (Vendor and Customer fields are displayed as read-only).
8. WHEN the user submits the edit form, THE Form_Schema SHALL validate: Validity From is on or before Validity To, and upon success THE Mapping_Page SHALL close the dialog, display a success Toast_Notification, and refresh the table data.
9. WHEN the user clicks the delete action on a row, THE Mapping_Page SHALL display a confirmation dialog stating that the mapping will be permanently removed.
10. WHEN the user confirms the deletion and the backend returns success, THE Mapping_Page SHALL display a success Toast_Notification and refresh the table data.
11. IF the backend returns a conflict or guard error when deleting a mapping, THEN THE Mapping_Page SHALL display a Toast_Notification with the specific error message from the backend.
12. WHEN the user clicks the "Bulk Upload" button, THE Mapping_Page SHALL open the Bulk_Upload_Dialog with entity_type set to "mapping".

---

### Requirement 9: Invoice Master Page

**User Story:** As a vendor agent or administrator, I want to create invoices with header and line items in a single form, view invoice lists, and update payment clearing details, so that I can manage the commission claim source transactions.

#### Acceptance Criteria

1. THE Invoice_Page SHALL display a paginated DataTable showing columns: Invoice Number, Invoice Date, Vendor Name, Customer Name, Bill Amount (excl. GST), Due Date, Payment Clearing Date, Invoice Status (Open/Payment Cleared/Settled tag), and Actions.
2. THE Invoice_Page SHALL support column-level search filtering on Invoice Number, Vendor Name, and Customer Name.
3. WHEN the user clicks the "New Invoice" button, THE Invoice_Page SHALL navigate to or open a creation form with header fields: Invoice Number (required), Invoice Date (required, date picker), Vendor (required, dropdown), Customer (required, dropdown), Bill Amount excl. GST (required, numeric), Bill Amount incl. Tax (numeric), Amount Deducted (numeric, default 0), TDS Value (numeric, default 0).
4. THE Invoice_Page creation form SHALL include a dynamic line items section where the user can add, edit, and remove invoice lines with fields: Product Detail (required, dropdown of active product details), Quantity (numeric), Line Amount (numeric), VAT/GST Amount (numeric).
5. WHEN the user submits the invoice creation form, THE Form_Schema SHALL validate: Invoice Number is non-empty, Invoice Date is provided, Vendor is selected, Customer is selected, Bill Amount excl. GST is a positive number, at least one line item exists with a Product Detail selected.
6. WHEN the invoice is successfully created, THE Invoice_Page SHALL display the auto-calculated Due Date (Invoice Date + Credit Days from the applicable Agreement) as a read-only field.
7. WHEN the user clicks the "Update Payment" action on an invoice with status Open, THE Invoice_Page SHALL open a dialog with fields: Payment Clearing Date (date picker), SAP Clearing Document No (text), and update the invoice status to Payment Cleared upon successful submission.
8. WHEN the user clicks the "Mark Settled" action on an invoice with status Payment Cleared, THE Invoice_Page SHALL display a confirmation dialog and update the invoice status to Settled upon confirmation.
9. IF the backend returns a conflict error (409) for duplicate Invoice Number, THEN THE Invoice_Page SHALL display a Toast_Notification with the specific conflict message.
10. THE Invoice_Page SHALL disable the "Update Payment" action for invoices that are not in Open status.
11. THE Invoice_Page SHALL disable the "Mark Settled" action for invoices that are not in Payment Cleared status.

---

### Requirement 10: User Create and Edit Page Updates

**User Story:** As an administrator, I want the Create User and Edit User pages to include the Entity dropdown, Validate with AD toggle, and the full field layout defined in the MASTERS_SPECIFICATION, so that users are properly linked to entities and authentication mode is configurable from the UI.

#### Acceptance Criteria

1. THE Create User page SHALL display fields: Employee ID (required), User Name (required), Email, First Name, Last Name, Password (conditional — required and min 8 characters unless "Validate with AD" is enabled), Validate with AD (toggle, default false), Roles (multi-select dropdown sourced from the application's existing roles table, defaults to none), Entity (dropdown of active entities formatted as "{Short Code} - {Entity Name}").
2. WHEN the user enables the "Validate with AD" toggle on the Create User page, THE form SHALL hide or disable the Password field and remove the password-required validation.
3. WHEN the user disables the "Validate with AD" toggle on the Create User page, THE form SHALL show the Password field and enforce the minimum 8 character requirement.
4. WHEN the user submits the Create User form, THE Form_Schema SHALL validate: Employee ID is non-empty, User Name is non-empty, Password is non-empty and at least 8 characters (when Validate with AD is disabled), Entity (if provided) references an active entity.
5. THE Edit User page SHALL display fields: Employee ID (read-only), User Name (read-only), Email (editable), First Name (editable, required), Last Name (editable, required), Roles (multi-select dropdown, fully replaces existing roles on save), Is Active (toggle — deactivating blocks login immediately), Validate with AD (toggle), Change Password (optional field — leave blank to keep current password, not applicable when Validate with AD is enabled), Entity (dropdown of active entities).
6. WHEN the user enables "Validate with AD" on the Edit User page, THE form SHALL hide or disable the Change Password field.
7. WHEN the user provides a value in the Change Password field on the Edit User page, THE Form_Schema SHALL validate that it is at least 8 characters.
8. WHEN the user leaves the Change Password field blank on the Edit User page, THE form SHALL not send a password change to the backend (keeping the existing password unchanged).
9. WHEN the user toggles "Is Active" to false and saves, THE Edit User page SHALL display a confirmation warning that the user will be immediately blocked from logging in.
10. THE Create User and Edit User pages SHALL use the same Entity dropdown component with the "{Short Code} - {Entity Name}" format and "Unknown" substitution as defined in Requirement 2 criterion 9.

---

### Requirement 11: Bulk Upload Dialog

**User Story:** As an administrator, I want a reusable bulk upload component that accepts a file and entity type parameter, validates the upload, and displays row-level results, so that I can efficiently import data into any master.

#### Acceptance Criteria

1. THE Bulk_Upload_Dialog SHALL accept an `entity_type` parameter to determine which master entity the upload applies to (vendor, customer, product_master, product_detail, agreement, mapping).
2. THE Bulk_Upload_Dialog SHALL provide a file input accepting CSV and Excel (.xlsx) file formats.
3. WHEN the user selects a file, THE Bulk_Upload_Dialog SHALL display the file name and size for confirmation before upload.
4. WHEN the user clicks "Upload", THE Bulk_Upload_Dialog SHALL submit the file to the `/bulk-upload` endpoint with the specified entity_type.
5. WHILE the upload is processing, THE Bulk_Upload_Dialog SHALL display a progress indicator (spinner) and disable the upload button.
6. WHEN the backend returns upload results, THE Bulk_Upload_Dialog SHALL display a summary: total rows processed, successful rows, and failed rows.
7. IF there are row-level errors, THEN THE Bulk_Upload_Dialog SHALL display a scrollable error table showing the row number and the specific error message for each failed row.
8. WHEN the user closes the Bulk_Upload_Dialog after a successful upload, THE Masters_UI SHALL refresh the parent table data automatically.
9. IF the uploaded file is malformed (wrong format, unreadable), THEN THE Bulk_Upload_Dialog SHALL display a Toast_Notification with the backend error message without showing the results panel.
10. THE Bulk_Upload_Dialog SHALL provide a "Download Template" link for each entity type so users can obtain the expected file format.

---

### Requirement 12: Form Validation and Error Handling

**User Story:** As a user, I want immediate client-side validation feedback on forms and clear server-side error messages, so that I can correct data entry issues efficiently.

#### Acceptance Criteria

1. THE Masters_UI SHALL validate all required fields on form submission using Zod schemas integrated with React Hook Form, displaying inline error messages below each invalid field.
2. WHEN a required field is left empty, THE Form_Schema SHALL display the message "This field is required" below the field.
3. WHEN a numeric field receives a non-numeric value, THE Form_Schema SHALL display a type-appropriate error message (e.g., "Must be a valid number").
4. WHEN the backend returns a validation error (422), THE Masters_UI SHALL map the error detail array to the corresponding form fields and display each field-level error inline.
5. WHEN the backend returns a business rule error (400 or 409), THE Masters_UI SHALL display the error detail message in a Toast_Notification with severity "error".
6. WHEN the backend returns a server error (500), THE Masters_UI SHALL display a generic "An unexpected error occurred. Please try again." Toast_Notification.
7. WHILE a form submission is in progress, THE Masters_UI SHALL disable the submit button and display a loading indicator to prevent duplicate submissions.

---

### Requirement 13: RBAC Permission Enforcement

**User Story:** As a system administrator, I want the masters UI to enforce role-based access control at the route, component, and field levels, so that users can only see and perform actions they are authorised for.

#### Acceptance Criteria

1. THE Masters_UI SHALL wrap each master page route with PrivateRoute using the appropriate menuKey for that master entity.
2. THE Masters_UI SHALL wrap create/edit action buttons with PermissionGate using the appropriate permission code (e.g., "vendors.create", "vendors.update").
3. THE Masters_UI SHALL wrap delete/deactivate action buttons with PermissionGate using the appropriate permission code (e.g., "vendors.deactivate", "customers.delete").
4. THE Masters_UI SHALL wrap the bulk upload button with PermissionGate using the appropriate permission code (e.g., "vendors.bulk_upload").
5. WHILE RBAC permissions are still loading, THE Masters_UI SHALL render no action buttons (avoid flash of unauthorised content).
6. THE Masters_UI SHALL use MenuGate to conditionally render sidebar navigation items based on the user's menu permissions.

---

### Requirement 14: Pagination, Sorting, and Server-State Management

**User Story:** As a user, I want paginated, sortable tables with efficient data fetching, so that I can browse large datasets without performance issues.

#### Acceptance Criteria

1. THE Masters_UI SHALL implement server-side pagination with configurable page sizes (10, 25, 50 rows per page) for all master list pages.
2. THE Masters_UI SHALL support column sorting by clicking column headers, passing sort parameters to the API.
3. THE Masters_UI SHALL use TanStack React Query hooks for all data fetching with a stale time of 30 seconds for list queries.
4. WHEN a mutation (create, update, delete, deactivate) succeeds, THE API_Hook SHALL invalidate the corresponding list query to trigger a data refresh.
5. WHILE data is loading for a list page, THE DataTable SHALL display the PrimeReact loading skeleton indicator.
6. WHEN a list query returns zero results, THE DataTable SHALL display the message "No records found."

---

### Requirement 15: Claim Validation Triangle Display

**User Story:** As a user viewing invoices, I want to see the eligibility status of each invoice for claim submission, so that I can understand which invoices are valid for commission claims without navigating to a separate screen.

#### Acceptance Criteria

1. WHEN the user clicks a "Check Eligibility" action on an invoice row, THE Invoice_Page SHALL display a read-only panel showing the three validation checks: active Agreement exists for Vendor + Product Detail covering the invoice date, active Mapping exists for Vendor + Customer as of the invoice date, and Invoice status is "Payment Cleared".
2. THE Invoice_Page SHALL display each validation check with a pass/fail indicator (green checkmark for pass, red cross for fail) and the specific reason for failure.
3. IF all three validation checks pass, THEN THE Invoice_Page SHALL display an overall "Eligible for Claim" status.
4. IF any validation check fails, THEN THE Invoice_Page SHALL display an overall "Not Eligible" status with the failed checks highlighted.

---

### Requirement 16: Responsive Layout and Accessibility

**User Story:** As a user, I want the masters UI to be usable on different screen sizes and accessible to keyboard and screen reader users, so that I can manage data effectively regardless of device or accessibility needs.

#### Acceptance Criteria

1. THE Masters_UI SHALL use PrimeReact responsive grid classes so that form dialogs and tables adapt to viewport widths down to 768px.
2. THE Masters_UI SHALL provide aria-label attributes on all DataTable components and form controls.
3. THE Masters_UI SHALL ensure all dialogs are keyboard-navigable (Tab, Shift+Tab, Escape to close).
4. THE Masters_UI SHALL ensure all action buttons have tooltip descriptions and accessible labels for screen readers.
5. THE Masters_UI SHALL use PrimeReact Tag components with appropriate severity styling for status displays, providing visual distinction without relying solely on colour.
