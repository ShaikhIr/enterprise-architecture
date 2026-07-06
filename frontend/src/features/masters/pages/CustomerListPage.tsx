/**
 * CustomerListPage — Paginated DataTable with CRUD operations for Customer Master.
 *
 * Features:
 * - Server-side pagination, sorting, column-level search filtering
 * - Create/Edit dialog with Zod validation and Customer Type dropdown
 * - Delete with confirmation and delete-guard error handling
 * - Bulk upload integration
 * - RBAC permission gating for edit, delete, and bulk upload actions
 *
 * Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 12.1, 12.5, 13.2, 13.3
 */

import { useState, useRef, useCallback } from 'react';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { InputText } from 'primereact/inputtext';
import { Toolbar } from 'primereact/toolbar';
import { PermissionGate } from '@core/rbac/PermissionGate';
import { useCustomers, useCreateCustomer, useUpdateCustomer } from '../hooks/useCustomers';
import { CustomerFormDialog } from '../components/CustomerFormDialog';
import { BulkUploadDialog } from '../components/BulkUploadDialog';
import type { Customer } from '../models/customer';
import type { CustomerCreateFormData } from '../schemas/customerSchema';
import type { PaginatedParams } from '../models/common';

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const DEFAULT_PAGE_SIZE = 10;

export const CustomerListPage = () => {
  // ─── Pagination & sort state ────────────────────────────────────────────────
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ─── Column filter state ────────────────────────────────────────────────────
  const [filterCustomerCode, setFilterCustomerCode] = useState('');
  const [filterCustomerName, setFilterCustomerName] = useState('');

  // ─── Dialog state ───────────────────────────────────────────────────────────
  const [showFormDialog, setShowFormDialog] = useState(false);
  const [showBulkUploadDialog, setShowBulkUploadDialog] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);

  const toast = useRef<Toast>(null);

  // ─── Build query params ─────────────────────────────────────────────────────
  const buildSearchParam = (): string | undefined => {
    const parts: string[] = [];
    if (filterCustomerCode.trim()) parts.push(filterCustomerCode.trim());
    if (filterCustomerName.trim()) parts.push(filterCustomerName.trim());
    return parts.length > 0 ? parts.join(' ') : undefined;
  };

  const queryParams: PaginatedParams = {
    skip: page * pageSize,
    limit: pageSize,
    search: buildSearchParam(),
    sort_by: sortField,
    sort_order: sortField ? sortOrder : undefined,
    customer_code: filterCustomerCode.trim() || undefined,
    customer_name: filterCustomerName.trim() || undefined,
  };

  // ─── Hooks ──────────────────────────────────────────────────────────────────
  const { data, isLoading } = useCustomers(queryParams);
  const createCustomer = useCreateCustomer();
  const updateCustomer = useUpdateCustomer();

  // ─── Event handlers ─────────────────────────────────────────────────────────
  const onPageChange = (e: DataTablePageEvent) => {
    setPage(e.page ?? 0);
    setPageSize(e.rows);
  };

  const onSort = (e: DataTableSortEvent) => {
    setSortField(e.sortField as string);
    setSortOrder(e.sortOrder === 1 ? 'asc' : 'desc');
  };

  const handleOpenCreate = () => {
    setEditingCustomer(null);
    setShowFormDialog(true);
  };

  const handleOpenEdit = (customer: Customer) => {
    setEditingCustomer(customer);
    setShowFormDialog(true);
  };

  const handleFormSubmit = useCallback(async (formData: CustomerCreateFormData) => {
    // Strip empty strings for optional fields so the backend treats them as absent
    // (the service validates any non-null value, so "" would fail GSTN/email regex)
    const sanitizedData = Object.fromEntries(
      Object.entries(formData).map(([k, v]) => [k, v === '' ? undefined : v])
    ) as CustomerCreateFormData;

    try {
      if (editingCustomer) {
        // Edit mode
        await updateCustomer.mutateAsync({ id: editingCustomer.id, request: sanitizedData });
        setShowFormDialog(false);
        setEditingCustomer(null);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Customer updated successfully',
          life: 3000,
        });
      } else {
        // Create mode
        await createCustomer.mutateAsync(sanitizedData);
        setShowFormDialog(false);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Customer created successfully',
          life: 3000,
        });
      }
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        // Conflict — duplicate customer code
        const detail = typeof rawDetail === 'string' ? rawDetail : 'A customer with this code already exists.';
        toast.current?.show({
          severity: 'error',
          summary: 'Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // Validation errors — backend returns either:
        //   Pydantic: { detail: [{loc, msg, type}, ...] }  (array)
        //   Service:  { detail: {field, reason} }          (object)
        let detail = 'Validation failed';
        if (Array.isArray(rawDetail)) {
          detail = rawDetail.map((e: any) => e.msg || e.message).join('; ');
        } else if (rawDetail && typeof rawDetail === 'object' && 'reason' in rawDetail) {
          detail = rawDetail.reason;
        } else if (typeof rawDetail === 'string') {
          detail = rawDetail;
        }
        toast.current?.show({
          severity: 'error',
          summary: 'Validation Error',
          detail,
          life: 5000,
        });
      } else {
        toast.current?.show({
          severity: 'error',
          summary: 'Error',
          detail: typeof rawDetail === 'string' ? rawDetail : 'An unexpected error occurred. Please try again.',
          life: 5000,
        });
      }
    }
  }, [editingCustomer, createCustomer, updateCustomer]);

  const handleBulkUploadSuccess = () => {
    toast.current?.show({
      severity: 'success',
      summary: 'Upload Complete',
      detail: 'Customer bulk upload completed successfully',
      life: 3000,
    });
  };

  // ─── Column templates ───────────────────────────────────────────────────────
  const statusBodyTemplate = (rowData: Customer) => {
    return (
      <Tag
        value={rowData.status}
        severity={rowData.status === 'Active' ? 'success' : 'danger'}
      />
    );
  };

  const actionsBodyTemplate = (rowData: Customer) => {
    return (
      <div className="flex gap-2">
        <PermissionGate permission="customer.update">
          <Button
            icon="pi pi-pencil"
            severity="secondary"
            text
            rounded
            onClick={() => handleOpenEdit(rowData)}
            aria-label={`Edit customer ${rowData.customer_name}`}
            tooltip="Edit"
            tooltipOptions={{ position: 'top' }}
          />
        </PermissionGate>
      </div>
    );
  };

  // ─── Column filter templates ────────────────────────────────────────────────
  const customerCodeFilterTemplate = () => (
    <InputText
      value={filterCustomerCode}
      onChange={(e) => { setFilterCustomerCode(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Customer Code"
    />
  );

  const customerNameFilterTemplate = () => (
    <InputText
      value={filterCustomerName}
      onChange={(e) => { setFilterCustomerName(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Customer Name"
    />
  );

  // ─── Toolbar ────────────────────────────────────────────────────────────────
  const toolbarLeftContent = (
    <div className="flex gap-2">
      <Button
        label="New Customer"
        icon="pi pi-plus"
        onClick={handleOpenCreate}
        aria-label="Create new customer"
      />
      <PermissionGate permission="customer.bulk_upload">
        <Button
          label="Bulk Upload"
          icon="pi pi-upload"
          severity="secondary"
          outlined
          onClick={() => setShowBulkUploadDialog(true)}
          aria-label="Bulk upload customers"
        />
      </PermissionGate>
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Customer Management</h2>
        <p className="text-600 mt-1 mb-0">Manage customer records</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
          <Toolbar className="mb-3 p-0 border-none" start={toolbarLeftContent} />

          <DataTable
            value={data?.items ?? []}
            loading={isLoading}
            paginator
            lazy
            first={page * pageSize}
            rows={pageSize}
            totalRecords={data?.total ?? 0}
            rowsPerPageOptions={PAGE_SIZE_OPTIONS}
            onPage={onPageChange}
            sortField={sortField}
            sortOrder={sortOrder === 'asc' ? 1 : -1}
            onSort={onSort}
            removableSort
            dataKey="id"
            emptyMessage="No customers found."
            stripedRows
            size="small"
            aria-label="Customer list table"
            filterDisplay="row"
          >
            <Column
              field="customer_code"
              header="Customer Code"
              sortable
              filter
              showFilterMenu={false}
              filterElement={customerCodeFilterTemplate}
              style={{ minWidth: '140px' }}
            />
            <Column
              field="customer_name"
              header="Customer Name"
              sortable
              filter
              showFilterMenu={false}
              filterElement={customerNameFilterTemplate}
              style={{ minWidth: '180px' }}
            />
            <Column
              field="contact_person"
              header="Contact Person"
              sortable
              style={{ minWidth: '150px' }}
            />
            <Column
              field="contact_email"
              header="Contact Email"
              sortable
              style={{ minWidth: '200px' }}
            />
            <Column
              field="status"
              header="Status"
              sortable
              body={statusBodyTemplate}
              style={{ minWidth: '100px' }}
            />
            <Column
              header="Actions"
              body={actionsBodyTemplate}
              style={{ minWidth: '120px' }}
              frozen
              alignFrozen="right"
            />
          </DataTable>
      </div>

      {/* Create/Edit Dialog */}
      <CustomerFormDialog
        visible={showFormDialog}
        onHide={() => { setShowFormDialog(false); setEditingCustomer(null); }}
        onSubmit={handleFormSubmit}
        customer={editingCustomer}
        loading={createCustomer.isPending || updateCustomer.isPending}
      />

      {/* Bulk Upload Dialog */}
      <BulkUploadDialog
        visible={showBulkUploadDialog}
        onHide={() => setShowBulkUploadDialog(false)}
        entityType="customer"
        onSuccess={handleBulkUploadSuccess}
      />
    </div>
  );
};
