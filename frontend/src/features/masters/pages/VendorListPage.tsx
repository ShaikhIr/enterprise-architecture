/**
 * VendorListPage — Paginated DataTable with CRUD operations for Vendor Master.
 *
 * Features:
 * - Server-side pagination, sorting, column-level search filtering
 * - Create/Edit dialog with Zod validation
 * - Deactivation with confirmation dialog
 * - Bulk upload integration
 * - RBAC permission gating for edit, deactivate, and bulk upload actions
 *
 * Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 12.1, 12.5, 12.7, 13.2, 13.3, 13.4
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
import { useVendors, useCreateVendor, useUpdateVendor, useDeactivateVendor } from '../hooks/useVendors';
import { VendorFormDialog } from '../components/VendorFormDialog';
import { VendorDeactivateDialog } from '../components/VendorDeactivateDialog';
import { BulkUploadDialog } from '../components/BulkUploadDialog';
import type { Vendor } from '../models/vendor';
import type { VendorCreateFormData } from '../schemas/vendorSchema';
import type { PaginatedParams } from '../models/common';

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const DEFAULT_PAGE_SIZE = 10;

export const VendorListPage = () => {
  // ─── Pagination & sort state ────────────────────────────────────────────────
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ─── Column filter state ────────────────────────────────────────────────────
  const [filterVendorCode, setFilterVendorCode] = useState('');
  const [filterVendorName, setFilterVendorName] = useState('');
  const [filterVendorEmail, setFilterVendorEmail] = useState('');
  const [filterCity, setFilterCity] = useState('');

  // ─── Dialog state ───────────────────────────────────────────────────────────
  const [showFormDialog, setShowFormDialog] = useState(false);
  const [showDeactivateDialog, setShowDeactivateDialog] = useState(false);
  const [showBulkUploadDialog, setShowBulkUploadDialog] = useState(false);
  const [editingVendor, setEditingVendor] = useState<Vendor | null>(null);
  const [deactivatingVendor, setDeactivatingVendor] = useState<Vendor | null>(null);

  const toast = useRef<Toast>(null);

  // ─── Build query params ─────────────────────────────────────────────────────
  const buildSearchParam = (): string | undefined => {
    const parts: string[] = [];
    if (filterVendorCode.trim()) parts.push(filterVendorCode.trim());
    if (filterVendorName.trim()) parts.push(filterVendorName.trim());
    if (filterVendorEmail.trim()) parts.push(filterVendorEmail.trim());
    return parts.length > 0 ? parts.join(' ') : undefined;
  };

  const queryParams: PaginatedParams = {
    skip: page * pageSize,
    limit: pageSize,
    search: buildSearchParam(),
    sort_by: sortField,
    sort_order: sortField ? sortOrder : undefined,
    vendor_code: filterVendorCode.trim() || undefined,
    vendor_name: filterVendorName.trim() || undefined,
    vendor_email: filterVendorEmail.trim() || undefined,
    city: filterCity.trim() || undefined,
  };

  // ─── Hooks ──────────────────────────────────────────────────────────────────
  const { data, isLoading } = useVendors(queryParams);
  const createVendor = useCreateVendor();
  const updateVendor = useUpdateVendor();
  const deactivateVendor = useDeactivateVendor();

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
    setEditingVendor(null);
    setShowFormDialog(true);
  };

  const handleOpenEdit = (vendor: Vendor) => {
    setEditingVendor(vendor);
    setShowFormDialog(true);
  };

  const handleOpenDeactivate = (vendor: Vendor) => {
    setDeactivatingVendor(vendor);
    setShowDeactivateDialog(true);
  };

  const handleFormSubmit = useCallback(async (formData: VendorCreateFormData) => {
    try {
      if (editingVendor) {
        // Edit mode — send all fields including status
        await updateVendor.mutateAsync({ id: editingVendor.id, request: formData });
        setShowFormDialog(false);
        setEditingVendor(null);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Vendor updated successfully',
          life: 3000,
        });
      } else {
        // Create mode — strip status (new vendors are always Active)
        const { status: _status, ...createData } = formData;
        await createVendor.mutateAsync(createData);
        setShowFormDialog(false);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Vendor and portal login have been provisioned.',
          life: 3000,
        });
      }
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        // Conflict — show toast with backend message
        const detail = typeof rawDetail === 'string' ? rawDetail : 'A vendor with this code or email already exists.';
        toast.current?.show({
          severity: 'error',
          summary: 'Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // Validation errors — show toast (inline errors handled by form if possible)
        const detail = Array.isArray(rawDetail)
          ? rawDetail.map((e: any) => e.msg || e.message).join('; ')
          : (typeof rawDetail === 'string' ? rawDetail : 'Validation failed');
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
  }, [editingVendor, createVendor, updateVendor]);

  const handleDeactivateConfirm = useCallback(async () => {
    if (!deactivatingVendor) return;
    try {
      await deactivateVendor.mutateAsync(deactivatingVendor.id);
      setShowDeactivateDialog(false);
      setDeactivatingVendor(null);
      // Also close the edit dialog if it was open
      setShowFormDialog(false);
      setEditingVendor(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Vendor deactivated successfully',
        life: 3000,
      });
    } catch (error: any) {
      const rawDetail = error.response?.data?.detail;
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: typeof rawDetail === 'string' ? rawDetail : 'Failed to deactivate vendor',
        life: 5000,
      });
      setShowDeactivateDialog(false);
      setDeactivatingVendor(null);
    }
  }, [deactivatingVendor, deactivateVendor]);

  const handleBulkUploadSuccess = () => {
    toast.current?.show({
      severity: 'success',
      summary: 'Upload Complete',
      detail: 'Vendor bulk upload completed successfully',
      life: 3000,
    });
  };

  // ─── Column templates ───────────────────────────────────────────────────────
  const statusBodyTemplate = (rowData: Vendor) => {
    return (
      <Tag
        value={rowData.status}
        severity={rowData.status === 'Active' ? 'success' : 'danger'}
      />
    );
  };

  const actionsBodyTemplate = (rowData: Vendor) => {
    return (
      <div className="flex gap-2">
        <PermissionGate permission="vendor.update">
          <Button
            icon="pi pi-pencil"
            severity="secondary"
            text
            rounded
            onClick={() => handleOpenEdit(rowData)}
            aria-label={`Edit vendor ${rowData.vendor_name}`}
            tooltip="Edit"
            tooltipOptions={{ position: 'top' }}
          />
        </PermissionGate>
      </div>
    );
  };

  // ─── Column filter templates ────────────────────────────────────────────────
  const vendorCodeFilterTemplate = () => (
    <InputText
      value={filterVendorCode}
      onChange={(e) => { setFilterVendorCode(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Vendor Code"
    />
  );

  const vendorNameFilterTemplate = () => (
    <InputText
      value={filterVendorName}
      onChange={(e) => { setFilterVendorName(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Vendor Name"
    />
  );

  const vendorEmailFilterTemplate = () => (
    <InputText
      value={filterVendorEmail}
      onChange={(e) => { setFilterVendorEmail(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Vendor Email"
    />
  );

  const cityFilterTemplate = () => (
    <InputText
      value={filterCity}
      onChange={(e) => { setFilterCity(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by City"
    />
  );

  // ─── Toolbar ────────────────────────────────────────────────────────────────
  const toolbarLeftContent = (
    <div className="flex gap-2">
      <Button
        label="New Vendor"
        icon="pi pi-plus"
        onClick={handleOpenCreate}
        aria-label="Create new vendor"
      />
      <PermissionGate permission="vendor.bulk_upload">
        <Button
          label="Bulk Upload"
          icon="pi pi-upload"
          severity="secondary"
          outlined
          onClick={() => setShowBulkUploadDialog(true)}
          aria-label="Bulk upload vendors"
        />
      </PermissionGate>
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Vendor Management</h2>
        <p className="text-600 mt-1 mb-0">Manage vendor (liaisoning agent) records</p>
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
            emptyMessage="No vendors found."
            stripedRows
            size="small"
            aria-label="Vendor list table"
            filterDisplay="row"
          >
            <Column
              field="vendor_code"
              header="Vendor Code"
              sortable
              filter
              showFilterMenu={false}
              filterElement={vendorCodeFilterTemplate}
              style={{ minWidth: '130px' }}
            />
            <Column
              field="vendor_name"
              header="Vendor Name"
              sortable
              filter
              showFilterMenu={false}
              filterElement={vendorNameFilterTemplate}
              style={{ minWidth: '180px' }}
            />
            <Column
              field="vendor_email"
              header="Vendor Email"
              sortable
              filter
              showFilterMenu={false}
              filterElement={vendorEmailFilterTemplate}
              style={{ minWidth: '200px' }}
            />
            <Column
              field="vendor_contact"
              header="Contact"
              sortable
              style={{ minWidth: '130px' }}
            />
            <Column
              field="city"
              header="City"
              sortable
              filter
              showFilterMenu={false}
              filterElement={cityFilterTemplate}
              style={{ minWidth: '120px' }}
            />
            <Column
              field="gstn_number"
              header="GSTN Number"
              sortable
              style={{ minWidth: '160px' }}
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
      <VendorFormDialog
        visible={showFormDialog}
        onHide={() => { setShowFormDialog(false); setEditingVendor(null); }}
        onSubmit={handleFormSubmit}
        vendor={editingVendor}
        loading={createVendor.isPending || updateVendor.isPending}
      />

      {/* Deactivation Confirmation Dialog */}
      <VendorDeactivateDialog
        visible={showDeactivateDialog}
        onHide={() => { setShowDeactivateDialog(false); setDeactivatingVendor(null); }}
        onConfirm={handleDeactivateConfirm}
        vendorName={deactivatingVendor?.vendor_name}
        loading={deactivateVendor.isPending}
      />

      {/* Bulk Upload Dialog */}
      <BulkUploadDialog
        visible={showBulkUploadDialog}
        onHide={() => setShowBulkUploadDialog(false)}
        entityType="vendor"
        onSuccess={handleBulkUploadSuccess}
      />
    </div>
  );
};
