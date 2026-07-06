# Requirements Document

## Introduction

This feature implements the complete set of master entities for the LACM (Liaisoning Agent Commission Management) application, as defined in `MASTERS_SPECIFICATION.md`. It covers Entity Master, Vendor Master, Customer Master, Product Master and Product Detail, Agreement Master, Vendor–Customer Mapping, and Invoice Master (Header and Line), together with the cross-master relationships and the Claim Validation Triangle that governs commission claim eligibility.

The implementation MUST follow the existing backend layered architecture (Controller → Service → Repository Interface → Repository Implementation), the enterprise standards, and the existing folder structure of both the backend (`backend/src`) and the frontend. Every master inherits the standard audit columns provided by the existing `BaseModel`/`AuditMixin`, and all data changes are captured automatically by the existing audit logging mechanism.

This document does NOT define a new User Master or a new Roles table. The User pages described here are layered onto the application's existing authentication and RBAC schema: the existing `User` record (username, password_hash, is_active, is_blocked, is_validate_ad), the existing `UserDetails` record (employee_id, first_name, last_name, email), and the existing `Role` / `RoleAssignment` tables. The only structural addition to the user domain is an `entity_id` reference linking each user to one Entity. Existing roles MUST be reused exactly as already implemented; no roles are created, renamed, or altered.

## Glossary

- **Entity_Service**: The application component that manages Entity Master records and entity dropdowns.
- **User_Service**: The existing application component that manages user records, extended to support the entity reference and the Create/Edit User page behaviour.
- **Vendor_Service**: The application component that manages Vendor Master records and vendor portal-login provisioning.
- **Customer_Service**: The application component that manages Customer Master records.
- **Product_Service**: The application component that manages Product Master and Product Detail records.
- **Agreement_Service**: The application component that manages Agreement Master records, including commission slab parameters, renewal, and expiry.
- **Mapping_Service**: The application component that manages Vendor–Customer Mapping records.
- **Invoice_Service**: The application component that manages Invoice Master (Header) and Invoice Details (Line) records.
- **Claim_Validation_Service**: The application component that evaluates the Claim Validation Triangle for invoice lines at claim submission.
- **Bulk_Upload_Service**: The application component that processes bulk-upload files for masters that support import.
- **Scheduler**: The scheduled background job component that transitions Agreement and Mapping records to their expired states.
- **Entity**: A legal company entity (e.g. Emcure Pharmaceuticals Ltd). Each user belongs to exactly one Entity.
- **Vendor**: A liaisoning agent (external service vendor) that procures orders and raises commission claims.
- **Customer**: A government body, hospital, pharmacy, or institution serviced and invoiced by a vendor.
- **Product Master**: The base molecule/formulation record in the two-level product hierarchy.
- **Product Detail**: A billable SKU/child variant that references one Product Master; downstream entities always reference the Product Detail.
- **Agreement**: A record defining a vendor's commission entitlement for a specific Product Detail over a validity period.
- **Vendor–Customer Mapping**: A record authorising a vendor to service a specific customer within a date range.
- **Invoice Header**: The top-level invoice record raised by a vendor against a customer.
- **Invoice Line**: A product-level detail row belonging to one Invoice Header.
- **Business Code**: A human-readable unique business key (e.g. Vendor Code, Customer Code, Child Code) that is distinct from the system-generated UUID primary key.
- **Audit Fields**: The standard columns `created_by`, `created_date`, `modified_by`, `modified_date` plus the UUID `id`, populated automatically by the existing `AuditMixin`.
- **Active Directory (AD)**: The external identity provider used when a user authenticates with "Validate with AD" enabled.
- **Due Date**: The date by which an invoice payment is expected, computed as Invoice Date + Credit Days from the applicable Agreement.
- **Delay Days**: Payment Clearing Date minus Due Date.
- **Applicable Commission %**: The commission percentage resulting from the slab calculation rule for a given delay.

## Requirements

### Requirement 1: Entity Master CRUD

**User Story:** As an administrator, I want to manage legal company entities, so that every user can be associated with the organisation they belong to.

#### Acceptance Criteria

1. THE Entity_Service SHALL persist each Entity with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. IF a create-Entity or update-Entity request omits the required Entity Name or supplies it as an empty or whitespace-only value, or supplies an Entity Name longer than 255 characters, a Short Code longer than 50 characters, or a Company Code longer than 50 characters, THEN THE Entity_Service SHALL reject the request with a validation error identifying the invalid field and SHALL NOT persist or modify any Entity record.
3. WHEN a request to create an Entity is received with an Entity Name that, compared case-insensitively after trimming surrounding whitespace, equals the Entity Name of an existing Entity, THE Entity_Service SHALL reject the request with a conflict error indicating a duplicate Entity Name and SHALL NOT persist any Entity record.
4. WHEN a request to create an Entity is received with a Company Code that, compared case-insensitively after trimming surrounding whitespace, equals the Company Code of an existing Entity, THE Entity_Service SHALL reject the request with a conflict error indicating a duplicate Company Code and SHALL NOT persist any Entity record.
5. WHEN a request to create an Entity is received with a unique Entity Name and (where provided) a unique Company Code, THE Entity_Service SHALL store the Entity with Is Active defaulting to true.
6. WHEN a request to read an Entity by ID is received for an existing Entity, THE Entity_Service SHALL return that Entity record.
7. IF a request to read, update, or delete an Entity references an ID that does not exist, THEN THE Entity_Service SHALL return a not-found error and SHALL NOT modify any Entity record.
8. WHEN a request to update an existing Entity is received, THE Entity_Service SHALL apply only the supplied fields, SHALL leave all unsupplied fields unchanged, and SHALL preserve the Entity Name and Company Code uniqueness constraints.
9. WHEN a paginated list request is received, THE Entity_Service SHALL return Entity records constrained by the supplied skip value (integer, minimum 0, default 0) and limit value (integer, 1 to 100 inclusive, default 20) together with the total count of matching Entity records.
10. IF a list request supplies a skip value below 0 or a limit value outside the range 1 to 100, THEN THE Entity_Service SHALL reject the request with a validation error.
11. WHERE a list request supplies a search term of 1 to 100 characters, THE Entity_Service SHALL return only Entities whose Entity Name, Short Code, or Company Code contains the search term using a trimmed, case-insensitive substring match.
12. WHERE a list request supplies an active-status filter, THE Entity_Service SHALL return only Entities whose Is Active value matches the filter.

### Requirement 2: Entity Dropdown

**User Story:** As a user filling in forms, I want a list of selectable entities, so that I can associate records with the correct active entity.

#### Acceptance Criteria

1. WHEN a request for the Entity dropdown is received, THE Entity_Service SHALL include every Entity whose Is Active value is true and SHALL exclude every Entity whose Is Active value is false.
2. WHEN a request for the Entity dropdown is received and no Entity has an Is Active value of true, THE Entity_Service SHALL return an empty list.
3. WHEN the Entity_Service returns a dropdown item, THE Entity_Service SHALL format its display label as the Short Code, followed by a space, a hyphen, and a space, followed by the Entity Name.
4. WHERE a dropdown item's Short Code or Entity Name is null, empty, or whitespace-only, THE Entity_Service SHALL substitute `Unknown` for that missing part when formatting the display label.

### Requirement 3: User–Entity Relationship and User Import

**User Story:** As an administrator, I want each user linked to one entity and entities resolved automatically during HR import, so that multi-entity organisation is maintained without manual entity setup.

#### Acceptance Criteria

1. THE User_Service SHALL store an optional `entity_id` reference on each user record that points to exactly one Entity.
2. WHEN a user record is imported from the HR system, THE User_Service SHALL resolve the referenced Entity by Company Code when the imported Company Code is non-empty, and otherwise by Entity Name.
3. WHEN a user record is imported from the HR system and the resolved Entity does not exist, THE User_Service SHALL create the Entity first using the imported Company Code and Entity Name and then assign the imported user to the newly created Entity.
4. WHEN a user record is imported from the HR system and the resolved Entity already exists, THE User_Service SHALL assign the imported user to the existing Entity.
5. IF an imported user row supplies neither a non-empty Company Code nor a non-empty Entity Name, THEN THE User_Service SHALL reject that row with a row-level error, SHALL log the row-level error for later review, and SHALL continue processing the remaining rows.
6. WHEN a user is imported with an Employee ID that does not match an existing user, THE User_Service SHALL create the user; and WHEN the Employee ID matches an existing user, THE User_Service SHALL update that user.

### Requirement 4: Create User Page

**User Story:** As an administrator, I want to create a new user, so that staff can access the application with the correct roles and entity.

#### Acceptance Criteria

1. IF a create-user request omits the required Employee ID or User Name, or supplies either as an empty value, THEN THE User_Service SHALL reject the request with a validation error identifying the missing required field and SHALL NOT create any user.
2. WHEN a create-user request is received with an Employee ID that is already used by an existing user, THE User_Service SHALL reject the request with a conflict error indicating a duplicate Employee ID and SHALL NOT create any user.
3. WHEN a create-user request is received with a User Name that is already used by an existing user, THE User_Service SHALL reject the request with a conflict error indicating a duplicate User Name and SHALL NOT create any user.
4. IF a create-user request has Validate with AD disabled and supplies a password shorter than 8 characters or no password, THEN THE User_Service SHALL reject the request with a validation error and SHALL NOT create any user.
5. IF a create-user request supplies an Entity reference that does not match an existing active Entity, THEN THE User_Service SHALL reject the request with a validation error and SHALL NOT create any user.
6. IF a create-user request supplies one or more Roles that do not match existing roles in the application's roles schema, THEN THE User_Service SHALL reject the request with a validation error and SHALL NOT create any user.
7. WHERE a create-user request has Validate with AD enabled, THE User_Service SHALL create the user without requiring a password.
8. WHEN a create-user request is received with valid data, THE User_Service SHALL store the Employee ID, User Name, Email, First Name, and Last Name on the existing user and user-details schema, SHALL set the entity reference to the supplied Entity, and SHALL return a success response identifying the created user.
9. WHEN a create-user request supplies one or more valid Roles, THE User_Service SHALL assign those Roles using the application's existing roles and role-assignment schema.
10. WHERE a create-user request supplies no Roles, THE User_Service SHALL create the user with no role assignments.

### Requirement 5: Edit User Page

**User Story:** As an administrator, I want to edit an existing user, so that I can update contact details, roles, entity, activation state, and password.

#### Acceptance Criteria

1. WHEN an edit-user request is received, THE User_Service SHALL preserve the existing Employee ID and User Name without change.
2. IF an edit-user request references a user ID that does not exist, THEN THE User_Service SHALL return a not-found error and SHALL NOT modify any user.
3. IF an edit-user request supplies an Entity reference that does not match an existing active Entity, THEN THE User_Service SHALL reject the request with a validation error and SHALL NOT modify the user.
4. WHEN an edit-user request is received with valid data, THE User_Service SHALL update the Email, First Name, Last Name, and Entity reference with the supplied values and SHALL return a success response.
5. WHEN an edit-user request supplies a Roles set, THE User_Service SHALL replace the user's existing role assignments with the supplied Roles.
6. WHEN an edit-user request that sets Is Active to false is persisted successfully, THE User_Service SHALL block the user from authenticating.
7. WHILE an edit-user request that sets Is Active to false has not been fully persisted, THE User_Service SHALL continue to allow the user to authenticate.
8. WHERE an edit-user request enables Validate with AD, THE User_Service SHALL update the user so that no stored password is required for authentication.
9. WHERE an edit-user request supplies a non-empty Change Password value and Validate with AD is disabled, THE User_Service SHALL set the user's password to the supplied value without requiring the current password.
10. IF an edit-user request supplies a non-empty Change Password value shorter than 8 characters and Validate with AD is disabled, THEN THE User_Service SHALL reject the request with a validation error and SHALL NOT modify the user.
11. WHERE an edit-user request supplies an empty Change Password value, THE User_Service SHALL keep the user's existing password unchanged.

### Requirement 6: Vendor Master CRUD and Portal Provisioning

**User Story:** As an administrator, I want to manage liaisoning-agent vendors and automatically give each one a portal login, so that vendors can submit commission claims.

#### Acceptance Criteria

1. THE Vendor_Service SHALL persist each Vendor with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. IF a create-vendor request omits the required Vendor Code, Vendor Name, or Vendor Email, or supplies any of them as an empty value, THEN THE Vendor_Service SHALL reject the request with a validation error identifying the missing required field and SHALL NOT persist any Vendor record.
3. WHEN a create-vendor request is received with a Vendor Code that is already used by an existing Vendor, THE Vendor_Service SHALL reject the request with a conflict error indicating a duplicate Vendor Code and SHALL NOT persist any Vendor record.
4. WHEN a create-vendor request is received with a Vendor Email that is already used by an existing Vendor, THE Vendor_Service SHALL reject the request with a conflict error indicating a duplicate Vendor Email and SHALL NOT persist any Vendor record.
5. IF a create-vendor or update-vendor request supplies a Vendor Email that does not conform to email format, THEN THE Vendor_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Vendor record.
6. IF a create-vendor or update-vendor request supplies a GSTN Number that does not match the pattern `[A-Z0-9]{15}`, THEN THE Vendor_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Vendor record.
7. WHEN a create-vendor request is received with valid data, THE Vendor_Service SHALL store the Vendor with Status defaulting to `Active`.
8. WHEN a Vendor is created, THE Vendor_Service SHALL provision a portal-login user whose username equals the Vendor Code, SHALL set a system-default password, and SHALL set the Vendor's Portal User reference to the provisioned portal-login user.
9. WHEN a request to read a Vendor by ID is received for an existing Vendor, THE Vendor_Service SHALL return that Vendor record.
10. IF a request to read or update a Vendor references an ID that does not exist, THEN THE Vendor_Service SHALL return a not-found error and SHALL NOT modify any Vendor record.
11. WHEN a paginated list request is received, THE Vendor_Service SHALL return Vendor records constrained by the supplied skip value (integer, minimum 0, default 0) and limit value (integer, 1 to 100 inclusive, default 20) together with the total count of matching Vendor records.
12. IF a list request supplies a skip value below 0 or a limit value outside the range 1 to 100, THEN THE Vendor_Service SHALL reject the request with a validation error.

### Requirement 7: Vendor Deactivation

**User Story:** As an administrator, I want to deactivate a vendor, so that the vendor can no longer log in or submit claims while historical data is retained.

#### Acceptance Criteria

1. IF a deactivate-vendor request references a Vendor ID that does not exist, THEN THE Vendor_Service SHALL return a not-found error and SHALL NOT modify any Vendor record.
2. WHEN a deactivate-vendor request is received for an existing Vendor, THE Vendor_Service SHALL set the Vendor Status to `Inactive`.
3. WHEN a Vendor Status is set to `Inactive`, THE Vendor_Service SHALL invalidate the vendor portal user's active sessions within 5 seconds and SHALL block new logins for that portal user.
4. IF session invalidation fails while a Vendor Status is being set to `Inactive`, THEN THE Vendor_Service SHALL complete the deactivation.
5. WHILE a Vendor Status is `Inactive`, THE Claim_Validation_Service SHALL reject new claim submissions for that Vendor with an error indicating the Vendor is inactive.
6. WHEN a Vendor Status is set to `Inactive`, THE Vendor_Service SHALL preserve all of the Vendor's existing records unchanged.

### Requirement 8: Customer Master CRUD

**User Story:** As an administrator, I want to manage customers, so that vendors can be mapped to them and invoices can be raised against them.

#### Acceptance Criteria

1. THE Customer_Service SHALL persist each Customer with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. WHEN a create-customer request is received with a Customer Code that is already used by an existing Customer, THE Customer_Service SHALL reject the request with a conflict error indicating a duplicate Customer Code, and SHALL NOT persist any Customer record.
3. IF a create-customer or update-customer request supplies a Customer Type that is not one of `Government Medical Corporation`, `Hospital`, `Pharmacy`, `Institution`, or `Other`, THEN THE Customer_Service SHALL reject the request with a validation error identifying the invalid Customer Type and SHALL NOT persist or modify any Customer record.
4. IF a create-customer or update-customer request supplies a GSTN Number that does not match the pattern `[A-Z0-9]{15}`, THEN THE Customer_Service SHALL reject the request with a validation error identifying the invalid GSTN Number and SHALL NOT persist or modify any Customer record.
5. WHEN a create-customer request is received with valid data, THE Customer_Service SHALL store the Customer with Status defaulting to `Active`.
6. IF a delete-customer request references a Customer that is referenced by any active Vendor–Customer Mapping or any Invoice Header, THEN THE Customer_Service SHALL reject the deletion with a conflict error indicating the Customer is in use, and SHALL retain the Customer record unchanged.
7. WHEN a paginated list request is received, THE Customer_Service SHALL return Customer records constrained by the supplied skip value (integer, minimum 0, default 0) and limit value (integer, 1 to 100 inclusive, default 20) together with the total count of matching Customer records.
8. IF a create-customer or update-customer request omits the required Customer Code or Customer Name, or supplies either as an empty value, THEN THE Customer_Service SHALL reject the request with a validation error identifying the missing required field and SHALL NOT persist or modify any Customer record.
9. IF a create-customer or update-customer request supplies a Contact Person exceeding 100 characters, a Contact Number exceeding 20 characters, or a Contact Email that does not conform to email format, THEN THE Customer_Service SHALL reject the request with a validation error identifying the invalid field and SHALL NOT persist or modify any Customer record.
10. IF an update-customer, read-customer, or delete-customer request references a Customer UUID that does not exist, THEN THE Customer_Service SHALL reject the request with a not-found error and SHALL NOT modify any Customer record.

### Requirement 9: Product Master CRUD

**User Story:** As an administrator, I want to manage base products, so that billable product variants can be defined under them.

#### Acceptance Criteria

1. THE Product_Service SHALL persist each Product Master with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. IF a create or update Product Master request omits the required Basic Material Code or Product Name, or supplies either as an empty value, THEN THE Product_Service SHALL reject the request with a validation error identifying the missing required field and SHALL NOT persist or modify any Product Master record.
3. WHEN a create Product Master request is received with a Basic Material Code that is already used by an existing Product Master, THE Product_Service SHALL reject the request with a conflict error indicating a duplicate Basic Material Code and SHALL NOT persist any Product Master record.
4. WHEN a create Product Master request is received with valid data, THE Product_Service SHALL store the Product Master with Status defaulting to `Active`.
5. IF a delete Product Master request references a Product Master that has one or more Product Detail children, THEN THE Product_Service SHALL reject the deletion with a conflict error and SHALL retain the Product Master record and its children unchanged.
6. IF a read, update, or delete Product Master request references a UUID that does not exist, THEN THE Product_Service SHALL return a not-found error and SHALL NOT modify any Product Master record.
7. WHEN a paginated list request for Product Masters is received, THE Product_Service SHALL return Product Master records constrained by the supplied skip value (integer, minimum 0, default 0) and limit value (integer, 1 to 100 inclusive, default 20) together with the total count of matching Product Master records.

### Requirement 10: Product Detail CRUD

**User Story:** As an administrator, I want to manage billable product variants under a base product, so that agreements and invoices can reference precise SKUs.

#### Acceptance Criteria

1. THE Product_Service SHALL persist each Product Detail with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. IF a create or update Product Detail request omits the required Child Code or Product Master reference, or supplies either as an empty value, THEN THE Product_Service SHALL reject the request with a validation error identifying the missing required field and SHALL NOT persist or modify any Product Detail record.
3. WHEN a create Product Detail request is received with a Child Code that is already used by an existing Product Detail, THE Product_Service SHALL reject the request with a conflict error indicating a duplicate Child Code and SHALL NOT persist any Product Detail record.
4. IF a create Product Detail request references a Product Master UUID that does not match an existing Product Master, THEN THE Product_Service SHALL reject the request with a validation error and SHALL NOT persist any Product Detail record.
5. IF a create or update Product Detail request supplies an MRP below 0 or a Rate below 0, THEN THE Product_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Product Detail record.
6. IF a create or update Product Detail request supplies a GST % outside the range 0 to 100 inclusive, THEN THE Product_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Product Detail record.
7. WHEN a create Product Detail request is received with valid data, THE Product_Service SHALL store the Product Detail with Status defaulting to `Active`.
8. IF a read, update, or delete Product Detail request references a UUID that does not exist, THEN THE Product_Service SHALL return a not-found error and SHALL NOT modify any Product Detail record.
9. WHERE a Product Detail list request supplies a `product_master_id` filter, THE Product_Service SHALL return only Product Details belonging to that Product Master.
10. WHEN a Product Detail is displayed on a downstream screen, THE Product_Service SHALL resolve the product name by traversing the Product Detail to its parent Product Master and returning the parent's Product Name.

### Requirement 11: Agreement Master CRUD

**User Story:** As an administrator, I want to define a vendor's commission entitlement for a product variant over a validity period, so that commission can be calculated against invoices.

#### Acceptance Criteria

1. THE Agreement_Service SHALL persist each Agreement with a system-generated UUID primary key and the standard Audit Fields.
2. IF a create or update Agreement request references a Vendor or a Product Detail that does not exist, THEN THE Agreement_Service SHALL reject the request with a validation error.
3. IF a create or update Agreement request supplies a From Date later than the To Date, THEN THE Agreement_Service SHALL reject the request with a validation error.
4. IF a create or update Agreement request supplies a Min Commission % greater than the Max Commission %, THEN THE Agreement_Service SHALL reject the request with a validation error.
5. IF a create or update Agreement request supplies a Reduction %, Max Commission %, or Min Commission % outside the range 0 to 100 inclusive, THEN THE Agreement_Service SHALL reject the request with a validation error.
6. IF a create or update Agreement request supplies a Slab in Days that is not greater than 0 or a Credit Days that is below 0, THEN THE Agreement_Service SHALL reject the request with a validation error.
7. IF a create or update Agreement request would produce an active Agreement whose validity period (From Date through To Date, both endpoints inclusive) overlaps an existing active Agreement for the same Vendor and Product Detail combination — where two periods overlap when each period's From Date is on or before the other period's To Date — THEN THE Agreement_Service SHALL reject the request with a conflict error.
8. WHEN a create Agreement request is received, THE Agreement_Service SHALL populate the Agreement Type defaulting to `Original` and the Status defaulting to `Active` before applying field validation.
9. IF a create or update Agreement request supplies an Agreement Document whose file type is not PDF, JPEG, or PNG or whose size exceeds 10 MB, THEN THE Agreement_Service SHALL reject the request with a validation error.
10. WHERE an Agreement list request supplies a `vendor_id` filter, THE Agreement_Service SHALL return only Agreements belonging to that Vendor.
11. IF a read, update, renew, or delete Agreement request references a UUID that does not exist, THEN THE Agreement_Service SHALL return a not-found error and SHALL NOT modify any Agreement record.

### Requirement 12: Commission Slab Calculation

**User Story:** As the commission engine, I want a deterministic slab-based commission rule, so that applicable commission is computed consistently from payment delay.

#### Acceptance Criteria

1. WHEN the Agreement_Service computes Applicable Commission % and the Delay Days value is less than or equal to 0, THE Agreement_Service SHALL set the Applicable Commission % equal to the Max Commission %.
2. WHEN the Agreement_Service computes Applicable Commission % and the Delay Days value is greater than 0, THE Agreement_Service SHALL compute the bucket as the ceiling of Delay Days divided by Slab in Days and SHALL set the Applicable Commission % to the greater of (Max Commission % minus bucket multiplied by Reduction %) and the Min Commission %.
3. WHEN the Agreement_Service computes Delay Days, THE Agreement_Service SHALL compute it as the number of whole calendar days from the Due Date to the Payment Clearing Date (Payment Clearing Date minus Due Date).

### Requirement 13: Agreement Renewal and Expiry

**User Story:** As an administrator, I want agreements to be renewable and to expire automatically, so that commission entitlements remain accurate over time.

#### Acceptance Criteria

1. WHEN a renew-Agreement request is received for an existing Agreement, THE Agreement_Service SHALL set the prior Agreement's Status to `Renewed`.
2. WHEN a renew-Agreement request is received for an existing Agreement, THE Agreement_Service SHALL create a new Agreement with Agreement Type `Renewal` whose Prior Agreement reference points to the prior Agreement.
3. WHEN the prior Agreement referenced by a Renewal Agreement is deleted, THE Agreement_Service SHALL set the Renewal Agreement's Prior Agreement reference to null.
4. WHEN the Scheduler runs its daily job and finds an Agreement whose Status is `Active` and whose To Date is earlier than the current date, THE Agreement_Service SHALL set that Agreement's Status to `Expired`.
5. IF a claim is submitted against an invoice whose invoice date is later than an Agreement's To Date, THEN THE Claim_Validation_Service SHALL block the claim line with an error indicating the agreement has expired and SHALL leave the claim line unclaimed.
6. IF a renew-Agreement request references an Agreement that does not exist, THEN THE Agreement_Service SHALL return a not-found error and SHALL NOT create or modify any Agreement record.

### Requirement 14: Vendor–Customer Mapping CRUD

**User Story:** As an administrator, I want to authorise a vendor to service a specific customer within a date range, so that claim validation can confirm the vendor is permitted to invoice that customer.

#### Acceptance Criteria

1. THE Mapping_Service SHALL persist each Vendor–Customer Mapping with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. IF a create or update Mapping request references a Vendor or a Customer that does not exist, THEN THE Mapping_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Mapping record.
3. IF a create or update Mapping request supplies a Validity From later than the Validity To, THEN THE Mapping_Service SHALL reject the request with a validation error and SHALL NOT persist or modify any Mapping record.
4. IF a create or update Mapping request would produce an active Mapping whose validity period (Validity From through Validity To, both endpoints inclusive) overlaps an existing active Mapping for the same Vendor and Customer combination, THEN THE Mapping_Service SHALL reject the request with a conflict error and SHALL NOT persist or modify any Mapping record.
5. WHEN a create Mapping request is received with valid data, THE Mapping_Service SHALL store the Mapping with Status set to `Active`.
6. WHEN an update Mapping request is received, THE Mapping_Service SHALL update only the Validity From and Validity To values and SHALL leave all other fields, including Status, unchanged.
7. WHERE a Mapping list request supplies a `vendor_id` filter, a `customer_id` filter, or both, THE Mapping_Service SHALL return only Mappings matching all supplied filters.
8. WHEN a Mapping list request matches no Mappings, THE Mapping_Service SHALL return an empty list.
9. IF a read, update, or delete Mapping request references a UUID that does not exist, THEN THE Mapping_Service SHALL return a not-found error and SHALL NOT modify any Mapping record.

### Requirement 15: Mapping Expiry

**User Story:** As an administrator, I want vendor–customer mappings to expire automatically, so that authorisation reflects the current date.

#### Acceptance Criteria

1. WHEN the Scheduler runs its end-of-day job, THE Mapping_Service SHALL set the Status to `Expired` for every Mapping whose Status is `Active` and whose Validity To is earlier than the current date.
2. WHEN the Scheduler runs its end-of-day job, THE Mapping_Service SHALL leave unchanged every active Mapping whose Validity To is on or after the current date.
3. IF the end-of-day expiry job fails before completion, THEN THE Mapping_Service SHALL leave the affected Mappings unchanged and SHALL retry the expiry on its next scheduled run.

### Requirement 16: Invoice Master (Header and Line)

**User Story:** As an administrator, I want to record vendor invoices against customers with their product lines, so that they can serve as the source transactions for commission claims.

#### Acceptance Criteria

1. THE Invoice_Service SHALL persist each Invoice Header with a system-generated UUID primary key and the standard Audit Fields (created by, created at, modified by, modified at).
2. WHEN a create Invoice request is received with an Invoice Number that is already used by an existing Invoice Header, THE Invoice_Service SHALL reject the request with a conflict error indicating the Invoice Number is already in use and SHALL NOT persist any Invoice Header or Invoice Line.
3. IF a create Invoice request references a Vendor or a Customer that does not exist, THEN THE Invoice_Service SHALL reject the request with a validation error identifying the missing reference and SHALL NOT persist any Invoice Header or Invoice Line.
4. IF an Invoice Line references a Product Detail that does not exist, THEN THE Invoice_Service SHALL reject the request with a validation error identifying the invalid Product Detail and SHALL NOT persist any Invoice Header or Invoice Line.
5. WHEN a create Invoice request is received with valid data, THE Invoice_Service SHALL store the Invoice Header with Amount Deducted defaulting to 0, TDS Value defaulting to 0, and Invoice Status defaulting to `Open`.
6. WHERE a create Invoice request does not supply a Due Date and an applicable Agreement with a defined Credit Days value exists, THE Invoice_Service SHALL compute the Due Date as the Invoice Date plus the Credit Days from that Agreement.
7. WHERE a create or update Invoice request supplies a Due Date, THE Invoice_Service SHALL store the supplied Due Date in place of the computed value.
8. WHERE a create Invoice request does not supply a Due Date and no applicable Agreement with a defined Credit Days value exists, THE Invoice_Service SHALL store the Invoice Header with an unset Due Date.
9. WHEN an Invoice Header is deleted, THE Invoice_Service SHALL delete all Invoice Lines belonging to that Invoice Header.

### Requirement 17: Invoice Status Lifecycle

**User Story:** As the commission system, I want invoices to follow a defined status lifecycle, so that only eligible invoices can be claimed and settled invoices cannot be reused.

#### Acceptance Criteria

1. WHEN payment confirmation is received from SAP for an existing Invoice Header, THE Invoice_Service SHALL set the Payment Clearing Date and the SAP Clearing Document No to the supplied values and SHALL set the Invoice Status to `Payment Cleared`.
2. WHEN a claim covering an Invoice Header reaches final approval, THE Invoice_Service SHALL set that Invoice Header's Status to `Settled`.
3. IF a new claim attempts to include an Invoice Header whose Status is `Settled`, THEN THE Claim_Validation_Service SHALL block that invoice line with an error indicating the invoice is already settled and SHALL NOT include the line in the claim.
4. IF SAP payment confirmation references an Invoice Number or Invoice Header that does not exist, THEN THE Invoice_Service SHALL reject the confirmation with a not-found error and SHALL NOT modify any Invoice Header.

### Requirement 18: Claim Validation Triangle

**User Story:** As a vendor submitting a claim, I want each invoice line validated against agreements, mappings, and invoice status, so that only legitimate commission claims proceed.

#### Acceptance Criteria

1. IF no Agreement with Status `Active` exists for the invoice line's Vendor and Product Detail whose validity period (From Date through To Date, inclusive) includes the invoice date, THEN THE Claim_Validation_Service SHALL block that invoice line and SHALL return an error identifying the affected line and indicating no active agreement covers the invoice date.
2. IF no Vendor–Customer Mapping with Status `Active` exists for the invoice line's Vendor and Customer whose validity period (Validity From through Validity To, inclusive) includes the invoice date, THEN THE Claim_Validation_Service SHALL block that invoice line and SHALL return an error identifying the affected line and indicating no active mapping covers the invoice date.
3. IF the invoice line's Invoice Header Status is not `Payment Cleared`, THEN THE Claim_Validation_Service SHALL block that invoice line and SHALL return an error identifying the affected line and indicating the invoice is not eligible for claim.
4. WHEN an invoice line satisfies an active Agreement, an active Vendor–Customer Mapping, and an Invoice Status of `Payment Cleared`, THE Claim_Validation_Service SHALL allow that invoice line to proceed.
5. WHEN a claim contains a mixture of valid and blocked invoice lines, THE Claim_Validation_Service SHALL allow the valid lines to proceed and SHALL block only the invalid lines, without rejecting the entire claim.
6. WHEN an invoice line fails more than one of the Agreement, Mapping, and Invoice Status checks, THE Claim_Validation_Service SHALL evaluate all three checks and SHALL return one distinct error for each failed check.

### Requirement 19: Bulk Upload

**User Story:** As an administrator, I want to bulk-upload master records from files, so that I can load large data sets efficiently with clear error reporting.

#### Acceptance Criteria

1. WHERE a bulk-upload request supplies a file for Vendor, Customer, Product Master, Product Detail, Agreement, or Vendor–Customer Mapping, THE Bulk_Upload_Service SHALL process each row independently.
2. IF a bulk-upload file does not conform to the expected file structure and cannot be parsed, THEN THE Bulk_Upload_Service SHALL reject the entire file with an error and SHALL NOT store any row.
3. IF a bulk-upload row fails validation, THEN THE Bulk_Upload_Service SHALL skip that row without storing it and SHALL include a row-level error stating the row position and the reason in the result report.
4. WHEN a bulk-upload row references another master by its Business Code, THE Bulk_Upload_Service SHALL resolve the Business Code to the referenced record's UUID before storing the row.
5. IF a bulk-upload row references a Business Code that cannot be resolved to an existing record, THEN THE Bulk_Upload_Service SHALL skip that row without storing it and SHALL include a row-level error stating the row position and the unresolved Business Code in the result report.
6. WHEN a bulk-upload request completes, THE Bulk_Upload_Service SHALL return a report listing the count of rows received, the count of rows stored, the count of rows skipped, and the row-level errors for skipped rows.

### Requirement 20: Audit and Authorisation

**User Story:** As a compliance officer, I want all master changes audited and access controlled, so that the system meets enterprise governance standards.

#### Acceptance Criteria

1. WHEN a master record is created, updated, or deleted, THE System SHALL record an audit entry capturing the acting user, the operation type, the timestamp, and the old and new values of the changed fields.
2. IF a request to a master endpoint is made without a valid authenticated session, THEN THE System SHALL reject the request with an unauthorised error and SHALL NOT perform the requested operation.
3. IF an authenticated user without the required permission requests a master operation, THEN THE System SHALL reject the request with a forbidden error and SHALL NOT perform the requested operation.
4. WHILE the requesting user is a vendor agent, THE System SHALL restrict Agreement and Vendor–Customer Mapping list results to records belonging to that user's own Vendor and SHALL exclude every record belonging to any other Vendor.
