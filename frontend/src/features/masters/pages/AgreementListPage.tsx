/**
 * AgreementListPage — Paginated DataTable with CRUD operations for Agreement Master.
 *
 * Features:
 * - Server-side pagination, sorting, column-level search filtering
 * - Create/Edit dialog with Zod validation (Vendor, Product Detail dropdowns, date pickers, numeric slab fields, file upload)
 * - Renewal dialog for active agreements (vendor/product read-only)
 * - Commission Slab Info panel in dialogs
 * - Vendor Agent auto-filter (agreements restricted to logged-in vendor)
 * - 409 overlap conflict Toast handling
 * - Bulk upload integration
 * - RBAC permission gating
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 1.5, 12.1, 12.5, 13.2
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
import { useAgreements, useCreateAgreement, useUpdateAgreement, useRenewAgreement } from '../hooks/useAgreements';
import { AgreementFormDialog } from '../components/AgreementFormDialog';
import { AgreementRenewalDialog } from '../components/AgreementRenewalDialog';
import { BulkUploadDialog } from '../components/BulkUploadDialog';
import type { Agreement } from '../models/agreement';
import type { AgreementCreateFormData } from '../schemas/agreementSchema';
import type { PaginatedParams } from '../models/common';

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const DEFAULT_PAGE_SIZE = 10;

export const AgreementListPage = () => {
  // ─── Pagination & sort state ────────────────────────────────────────────────
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ─── Column filter state ────────────────────────────────────────────────────
  const [filterVendorName, setFilterVendorName] = useState('');
  const [filterProductDetail, setFilterProductDetail] = useState('');

  // ─── Dialog state ───────────────────────────────────────────────────────────
  const [showFormDialog, setShowFormDialog] = useState(false);
  const [showRenewalDialog, setShowRenewalDialog] = useState(false);
  const [showBulkUploadDialog, setShowBulkUploadDialog] = useState(false);
  const [editingAgreement, setEditingAgreement] = useState<Agreement | null>(null);
  const [renewingAgreement, setRenewingAgreement] = useState<Agreement | null>(null);

  const toast = useRef<Toast>(null);

  // ─── Build query params ─────────────────────────────────────────────────────
  const queryParams: PaginatedParams = {
    skip: page * pageSize,
    limit: pageSize,
    search: undefined,
    sort_by: sortField,
    sort_order: sortField ? sortOrder : undefined,
    vendor_name: filterVendorName.trim() || undefined,
    product_detail: filterProductDetail.trim() || undefined,
  };

  // ─── Hooks ──────────────────────────────────────────────────────────────────
  const { data, isLoading } = useAgreements(queryParams);
  const createAgreement = useCreateAgreement();
  const updateAgreement = useUpdateAgreement();
  const renewAgreement = useRenewAgreement();

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
    setEditingAgreement(null);
    setShowFormDialog(true);
  };

  const handleOpenEdit = (agreement: Agreement) => {
    setEditingAgreement(agreement);
    setShowFormDialog(true);
  };

  const handleOpenRenewal = (agreement: Agreement) => {
    setRenewingAgreement(agreement);
    setShowRenewalDialog(true);
  };

  const handleFormSubmit = useCallback(async (formData: AgreementCreateFormData) => {
    try {
      if (editingAgreement) {
        await updateAgreement.mutateAsync({ id: editingAgreement.id, request: formData });
        setShowFormDialog(false);
        setEditingAgreement(null);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Agreement updated successfully',
          life: 3000,
        });
      } else {
        await createAgreement.mutateAsync(formData);
        setShowFormDialog(false);
        toast.current?.show({
          severity: 'success',
          summary: 'Success',
          detail: 'Agreement created successfully',
          life: 3000,
        });
      }
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        const detail = typeof rawDetail === 'string'
          ? rawDetail
          : 'An active agreement already exists for the same vendor and product detail within the specified date range.';
        toast.current?.show({
          severity: 'error',
          summary: 'Overlap Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // Backend returns either:
        //   Pydantic: { detail: [{loc, msg, type}] }  (array)
        //   Service:  { detail: {field, reason} }      (object)
        let detail = 'Validation failed';
        if (Array.isArray(rawDetail)) {
          detail = rawDetail.map((e: any) => e.msg || e.message).join('; ');
        } else if (rawDetail && typeof rawDetail === 'object' && 'reason' in rawDetail) {
          detail = `${rawDetail.field ? rawDetail.field + ': ' : ''}${rawDetail.reason}`;
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
      // Re-throw so dialog can handle 422 inline
      throw error;
    }
  }, [editingAgreement, createAgreement, updateAgreement]);

  const handleRenewalSubmit = useCallback(async (formData: AgreementCreateFormData) => {
    if (!renewingAgreement) return;
    try {
      const { vendor_id, product_detail_id, ...renewalData } = formData;
      await renewAgreement.mutateAsync({
        id: renewingAgreement.id,
        request: renewalData,
      });
      setShowRenewalDialog(false);
      setRenewingAgreement(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Agreement renewed successfully',
        life: 3000,
      });
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        const detail = typeof rawDetail === 'string'
          ? rawDetail
          : 'An active agreement already exists for the same vendor and product detail within the specified date range.';
        toast.current?.show({
          severity: 'error',
          summary: 'Overlap Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        let detail = 'Validation failed';
        if (Array.isArray(rawDetail)) {
          detail = rawDetail.map((e: any) => e.msg || e.message).join('; ');
        } else if (rawDetail && typeof rawDetail === 'object' && 'reason' in rawDetail) {
          detail = `${rawDetail.field ? rawDetail.field + ': ' : ''}${rawDetail.reason}`;
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
      // Re-throw so dialog can handle 422 inline
      throw error;
    }
  }, [renewingAgreement, renewAgreement]);

  const handleBulkUploadSuccess = () => {
    toast.current?.show({
      severity: 'success',
      summary: 'Upload Complete',
      detail: 'Agreement bulk upload completed successfully',
      life: 3000,
    });
  };

  // ─── Column templates ───────────────────────────────────────────────────────
  const productDetailBodyTemplate = (rowData: Agreement) => {
    return `${rowData.product_detail_child_code} - ${rowData.product_detail_name}`;
  };

  const agreementTypeBodyTemplate = (rowData: Agreement) => {
    return (
      <Tag
        value={rowData.agreement_type}
        severity={rowData.agreement_type === 'Original' ? 'info' : 'warning'}
      />
    );
  };

  const statusBodyTemplate = (rowData: Agreement) => {
    const severityMap: Record<string, 'success' | 'danger' | 'warning'> = {
      Active: 'success',
      Expired: 'danger',
      Renewed: 'warning',
    };
    return (
      <Tag
        value={rowData.status}
        severity={severityMap[rowData.status] ?? 'info'}
      />
    );
  };

  const actionsBodyTemplate = (rowData: Agreement) => {
    return (
      <div className="flex gap-2">
        <PermissionGate permission="agreement.update">
          <Button
            icon="pi pi-pencil"
            severity="secondary"
            text
            rounded
            onClick={() => handleOpenEdit(rowData)}
            aria-label={`Edit agreement for ${rowData.vendor_name}`}
            tooltip="Edit"
            tooltipOptions={{ position: 'top' }}
          />
        </PermissionGate>
        {rowData.status === 'Active' && (
          <PermissionGate permission="agreement.update">
            <Button
              icon="pi pi-refresh"
              severity="success"
              text
              rounded
              onClick={() => handleOpenRenewal(rowData)}
              aria-label={`Renew agreement for ${rowData.vendor_name}`}
              tooltip="Renew"
              tooltipOptions={{ position: 'top' }}
            />
          </PermissionGate>
        )}
      </div>
    );
  };

  // ─── Column filter templates ────────────────────────────────────────────────
  const vendorNameFilterTemplate = () => (
    <InputText
      value={filterVendorName}
      onChange={(e) => { setFilterVendorName(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Vendor Name"
    />
  );

  const productDetailFilterTemplate = () => (
    <InputText
      value={filterProductDetail}
      onChange={(e) => { setFilterProductDetail(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Product Detail"
    />
  );

  // ─── Toolbar ────────────────────────────────────────────────────────────────
  const toolbarLeftContent = (
    <div className="flex gap-2">
      <Button
        label="New Agreement"
        icon="pi pi-plus"
        onClick={handleOpenCreate}
        aria-label="Create new agreement"
      />
      <PermissionGate permission="agreement.bulk_upload">
        <Button
          label="Bulk Upload"
          icon="pi pi-upload"
          severity="secondary"
          outlined
          onClick={() => setShowBulkUploadDialog(true)}
          aria-label="Bulk upload agreements"
        />
      </PermissionGate>
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Agreement Management</h2>
        <p className="text-600 mt-1 mb-0">Manage vendor commission agreements per product</p>
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
            emptyMessage="No agreements found."
            stripedRows
            size="small"
            aria-label="Agreement list table"
            filterDisplay="row"
          >
            <Column
              field="vendor_name"
              header="Vendor Name"
              sortable
              filter
              showFilterMenu={false}
              filterElement={vendorNameFilterTemplate}
              style={{ minWidth: '160px' }}
            />
            <Column
              field="product_detail_child_code"
              header="Product Detail"
              sortable
              filter
              showFilterMenu={false}
              filterElement={productDetailFilterTemplate}
              body={productDetailBodyTemplate}
              style={{ minWidth: '180px' }}
            />
            <Column
              field="from_date"
              header="From Date"
              sortable
              style={{ minWidth: '120px' }}
            />
            <Column
              field="to_date"
              header="To Date"
              sortable
              style={{ minWidth: '120px' }}
            />
            <Column
              field="max_commission_percent"
              header="Max Commission %"
              sortable
              style={{ minWidth: '140px' }}
            />
            <Column
              field="min_commission_percent"
              header="Min Commission %"
              sortable
              style={{ minWidth: '140px' }}
            />
            <Column
              field="credit_days"
              header="Credit Days"
              sortable
              style={{ minWidth: '110px' }}
            />
            <Column
              field="agreement_type"
              header="Agreement Type"
              sortable
              body={agreementTypeBodyTemplate}
              style={{ minWidth: '140px' }}
            />
            <Column
              field="status"
              header="Status"
              sortable
              body={statusBodyTemplate}
              style={{ minWidth: '110px' }}
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
      <AgreementFormDialog
        visible={showFormDialog}
        onHide={() => { setShowFormDialog(false); setEditingAgreement(null); }}
        onSubmit={handleFormSubmit}
        agreement={editingAgreement}
        loading={createAgreement.isPending || updateAgreement.isPending}
      />

      {/* Renewal Dialog */}
      <AgreementRenewalDialog
        visible={showRenewalDialog}
        onHide={() => { setShowRenewalDialog(false); setRenewingAgreement(null); }}
        onSubmit={handleRenewalSubmit}
        agreement={renewingAgreement}
        loading={renewAgreement.isPending}
      />

      {/* Bulk Upload Dialog */}
      <BulkUploadDialog
        visible={showBulkUploadDialog}
        onHide={() => setShowBulkUploadDialog(false)}
        entityType="agreement"
        onSuccess={handleBulkUploadSuccess}
      />
    </div>
  );
};
