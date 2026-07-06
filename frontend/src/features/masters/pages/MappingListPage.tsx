/**
 * MappingListPage — Paginated DataTable with CRUD operations for Vendor–Customer Mapping.
 *
 * Features:
 * - Server-side pagination, sorting
 * - Dropdown filters for Vendor and Customer
 * - Vendor agent auto-filter from Redux auth state
 * - Create/Edit dialog with Zod validation
 * - Delete with confirmation dialog
 * - 409 overlap Toast, delete-guard Toast
 * - Bulk upload integration
 * - RBAC permission gating
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 1.5, 12.1, 12.5, 13.2, 13.3
 */

import { useState, useRef, useCallback } from 'react';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { Dropdown } from 'primereact/dropdown';
import { Toolbar } from 'primereact/toolbar';
import { PermissionGate } from '@core/rbac/PermissionGate';
import { useAppSelector } from '@app/store';
import { useMappings, useCreateMapping, useUpdateMapping } from '../hooks/useMappings';
import { useVendors } from '../hooks/useVendors';
import { useCustomers } from '../hooks/useCustomers';
import { MappingFormDialog } from '../components/MappingFormDialog';
import { BulkUploadDialog } from '../components/BulkUploadDialog';
import type { VendorCustomerMapping } from '../models/mapping';
import type { MappingCreateFormData, MappingUpdateFormData } from '../schemas/mappingSchema';
import type { PaginatedParams } from '../models/common';

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const DEFAULT_PAGE_SIZE = 10;

export const MappingListPage = () => {
  // ─── Auth state (vendor agent auto-filter) ──────────────────────────────────
  const user = useAppSelector((state) => state.auth.user);
  const vendorAgentVendorId = user?.vendor_id ?? undefined;

  // ─── Pagination & sort state ────────────────────────────────────────────────
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ─── Filter state (dropdown filters) ───────────────────────────────────────
  const [filterVendorId, setFilterVendorId] = useState<string | null>(null);
  const [filterCustomerId, setFilterCustomerId] = useState<string | null>(null);

  // ─── Dialog state ───────────────────────────────────────────────────────────
  const [showFormDialog, setShowFormDialog] = useState(false);
  const [showBulkUploadDialog, setShowBulkUploadDialog] = useState(false);
  const [editingMapping, setEditingMapping] = useState<VendorCustomerMapping | null>(null);

  const toast = useRef<Toast>(null);

  // ─── Fetch vendors and customers for dropdown filters ───────────────────────
  const { data: vendorsData } = useVendors({ skip: 0, limit: 1000 });
  const { data: customersData } = useCustomers({ skip: 0, limit: 1000 });

  const vendorFilterOptions = [
    { label: 'All Vendors', value: null },
    ...(vendorsData?.items ?? []).map((v) => ({
      label: `${v.vendor_code} - ${v.vendor_name}`,
      value: v.id,
    })),
  ];

  const customerFilterOptions = [
    { label: 'All Customers', value: null },
    ...(customersData?.items ?? []).map((c) => ({
      label: `${c.customer_code} - ${c.customer_name}`,
      value: c.id,
    })),
  ];

  // ─── Build query params ─────────────────────────────────────────────────────
  const queryParams: PaginatedParams = {
    skip: page * pageSize,
    limit: pageSize,
    sort_by: sortField,
    sort_order: sortField ? sortOrder : undefined,
    // Vendor agent auto-filter takes precedence over dropdown filter
    ...(vendorAgentVendorId
      ? { vendor_id: vendorAgentVendorId }
      : filterVendorId ? { vendor_id: filterVendorId } : {}),
    ...(filterCustomerId ? { customer_id: filterCustomerId } : {}),
  };

  // ─── Hooks ──────────────────────────────────────────────────────────────────
  const { data, isLoading } = useMappings(queryParams);
  const createMapping = useCreateMapping();
  const updateMapping = useUpdateMapping();

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
    setEditingMapping(null);
    setShowFormDialog(true);
  };

  const handleOpenEdit = (mapping: VendorCustomerMapping) => {
    setEditingMapping(mapping);
    setShowFormDialog(true);
  };

  const handleFormSubmit = useCallback(async (formData: MappingCreateFormData | MappingUpdateFormData) => {
    try {
      if (editingMapping) {
        // Edit mode — only dates
        const updateData = formData as MappingUpdateFormData;
        await updateMapping.mutateAsync({
          id: editingMapping.id,
          request: {
            validity_from: updateData.validity_from,
            validity_to: updateData.validity_to,
          },
        });
        setShowFormDialog(false);
        setEditingMapping(null);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Mapping updated successfully',
          life: 3000,
        });
      } else {
        // Create mode
        await createMapping.mutateAsync(formData as MappingCreateFormData);
        setShowFormDialog(false);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Mapping created successfully',
          life: 3000,
        });
      }
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        // Overlap conflict
        const detail = typeof rawDetail === 'string'
          ? rawDetail
          : 'An active mapping already exists for the same vendor and customer within the specified date range.';
        toast.current?.show({
          severity: 'error',
          summary: 'Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // Validation errors — rethrow so dialog can handle inline errors
        throw error;
      } else {
        toast.current?.show({
          severity: 'error',
          summary: 'Error',
          detail: typeof rawDetail === 'string' ? rawDetail : 'An unexpected error occurred. Please try again.',
          life: 5000,
        });
      }
    }
  }, [editingMapping, createMapping, updateMapping]);

  const handleBulkUploadSuccess = () => {
    toast.current?.show({
      severity: 'success',
      summary: 'Upload Complete',
      detail: 'Mapping bulk upload completed successfully',
      life: 3000,
    });
  };

  // ─── Column templates ───────────────────────────────────────────────────────
  const statusBodyTemplate = (rowData: VendorCustomerMapping) => (
    <Tag
      value={rowData.status}
      severity={rowData.status === 'Active' ? 'success' : 'warning'}
    />
  );

  const actionsBodyTemplate = (rowData: VendorCustomerMapping) => (
    <div className="flex gap-2">
      <PermissionGate permission="mapping.update">
        <Button
          icon="pi pi-pencil"
          severity="secondary"
          text
          rounded
          onClick={() => handleOpenEdit(rowData)}
          aria-label={`Edit mapping ${rowData.vendor_name} - ${rowData.customer_name}`}
          tooltip="Edit"
          tooltipOptions={{ position: 'top' }}
        />
      </PermissionGate>
    </div>
  );

  // ─── Toolbar ────────────────────────────────────────────────────────────────
  const toolbarLeftContent = (
    <div className="flex gap-2">
      <Button
        label="New Mapping"
        icon="pi pi-plus"
        onClick={handleOpenCreate}
        aria-label="Create new mapping"
      />
      <PermissionGate permission="mapping.bulk_upload">
        <Button
          label="Bulk Upload"
          icon="pi pi-upload"
          severity="secondary"
          outlined
          onClick={() => setShowBulkUploadDialog(true)}
          aria-label="Bulk upload mappings"
        />
      </PermissionGate>
    </div>
  );

  const toolbarRightContent = (
    <div className="flex align-items-center gap-2">
      {/* Vendor dropdown filter (hidden for vendor agents since auto-filtered) */}
      {!vendorAgentVendorId && (
        <Dropdown
          value={filterVendorId}
          onChange={(e) => { setFilterVendorId(e.value); setPage(0); }}
          options={vendorFilterOptions}
          optionLabel="label"
          optionValue="value"
          placeholder="Filter by Vendor"
          filter
          filterPlaceholder="Search vendors..."
          className="w-15rem"
          aria-label="Filter table by vendor"
        />
      )}
      {/* Customer dropdown filter */}
      <Dropdown
        value={filterCustomerId}
        onChange={(e) => { setFilterCustomerId(e.value); setPage(0); }}
        options={customerFilterOptions}
        optionLabel="label"
        optionValue="value"
        placeholder="Filter by Customer"
        filter
        filterPlaceholder="Search customers..."
        className="w-15rem"
        aria-label="Filter table by customer"
      />
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Vendor–Customer Mapping</h2>
        <p className="text-600 mt-1 mb-0">Manage vendor-customer mapping records</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
          <Toolbar className="mb-3 p-0 border-none" start={toolbarLeftContent} end={toolbarRightContent} />

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
            emptyMessage="No mappings found."
            stripedRows
            size="small"
            aria-label="Mapping list table"
          >
            <Column
              field="vendor_name"
              header="Vendor Name"
              sortable
              style={{ minWidth: '180px' }}
            />
            <Column
              field="customer_name"
              header="Customer Name"
              sortable
              style={{ minWidth: '180px' }}
            />
            <Column
              field="validity_from"
              header="Validity From"
              sortable
              style={{ minWidth: '130px' }}
            />
            <Column
              field="validity_to"
              header="Validity To"
              sortable
              style={{ minWidth: '130px' }}
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
      <MappingFormDialog
        visible={showFormDialog}
        onHide={() => { setShowFormDialog(false); setEditingMapping(null); }}
        onSubmit={handleFormSubmit}
        mapping={editingMapping}
        loading={createMapping.isPending || updateMapping.isPending}
      />

      {/* Bulk Upload Dialog */}
      <BulkUploadDialog
        visible={showBulkUploadDialog}
        onHide={() => setShowBulkUploadDialog(false)}
        entityType="mapping"
        onSuccess={handleBulkUploadSuccess}
      />
    </div>
  );
};
