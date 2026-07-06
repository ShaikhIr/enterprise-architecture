/**
 * InvoiceListPage — Paginated DataTable with lifecycle operations for Invoice Master.
 *
 * Features:
 * - Server-side pagination, sorting, column-level search filtering
 * - Create invoice dialog with Zod validation and line items
 * - Update Payment dialog (disabled for non-Open invoices)
 * - Mark Settled confirmation (disabled for non-Payment Cleared invoices)
 * - Check Eligibility panel (3-check claim validation triangle)
 * - 409 duplicate invoice number Toast
 * - Display auto-calculated Due Date as read-only
 *
 * Requirements: 9.1-9.11, 12.1, 12.5, 13.2, 15.1-15.4
 */

import { useState, useRef, useCallback } from 'react';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { InputText } from 'primereact/inputtext';
import { Toolbar } from 'primereact/toolbar';
import { useInvoices, useCreateInvoice, useUpdatePayment, useMarkSettled } from '../hooks/useInvoices';
import { InvoiceForm } from '../components/InvoiceForm';
import { PaymentUpdateDialog } from '../components/PaymentUpdateDialog';
import { SettleConfirmDialog } from '../components/SettleConfirmDialog';
import { EligibilityPanel } from '../components/EligibilityPanel';
import { InvoiceLineViewDialog } from '../components/InvoiceLineViewDialog';
import type { Invoice } from '../models/invoice';
import type { InvoiceCreateFormData } from '../schemas/invoiceSchema';
import type { PaginatedParams } from '../models/common';

const PAGE_SIZE_OPTIONS = [10, 25, 50];
const DEFAULT_PAGE_SIZE = 10;

export const InvoiceListPage = () => {
  // ─── Pagination & sort state ────────────────────────────────────────────────
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // ─── Column filter state ────────────────────────────────────────────────────
  const [filterInvoiceNumber, setFilterInvoiceNumber] = useState('');
  const [filterVendorName, setFilterVendorName] = useState('');
  const [filterCustomerName, setFilterCustomerName] = useState('');

  // ─── Dialog state ───────────────────────────────────────────────────────────
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showPaymentDialog, setShowPaymentDialog] = useState(false);
  const [showSettleDialog, setShowSettleDialog] = useState(false);
  const [showEligibilityPanel, setShowEligibilityPanel] = useState(false);
  const [showLinesDialog, setShowLinesDialog] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  const toast = useRef<Toast>(null);

  // ─── Build query params ─────────────────────────────────────────────────────
  const queryParams: PaginatedParams = {
    skip: page * pageSize,
    limit: pageSize,
    search: [filterInvoiceNumber, filterVendorName, filterCustomerName].filter(Boolean).join(' ') || undefined,
    sort_by: sortField,
    sort_order: sortField ? sortOrder : undefined,
    invoice_number: filterInvoiceNumber.trim() || undefined,
    vendor_name: filterVendorName.trim() || undefined,
    customer_name: filterCustomerName.trim() || undefined,
  };

  // ─── Hooks ──────────────────────────────────────────────────────────────────
  const { data, isLoading } = useInvoices(queryParams);
  const createInvoice = useCreateInvoice();
  const updatePayment = useUpdatePayment();
  const markSettled = useMarkSettled();

  // ─── Event handlers ─────────────────────────────────────────────────────────
  const onPageChange = (e: DataTablePageEvent) => {
    setPage(e.page ?? 0);
    setPageSize(e.rows);
  };

  const onSort = (e: DataTableSortEvent) => {
    setSortField(e.sortField as string);
    setSortOrder(e.sortOrder === 1 ? 'asc' : 'desc');
  };

  const handleCreateSubmit = useCallback(async (formData: InvoiceCreateFormData) => {
    try {
      await createInvoice.mutateAsync(formData);
      setShowCreateDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Invoice created successfully',
        life: 3000,
      });
    } catch (error: any) {
      const status = error.response?.status;
      const rawDetail = error.response?.data?.detail;

      if (status === 409) {
        toast.current?.show({
          severity: 'error',
          summary: 'Duplicate Invoice',
          detail: typeof rawDetail === 'string' ? rawDetail : 'An invoice with this number already exists.',
          life: 5000,
        });
      } else if (status === 422) {
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
  }, [createInvoice]);

  const handlePaymentSubmit = useCallback(async (formData: { payment_clearing_date: string; sap_clearing_doc_no: string }) => {
    if (!selectedInvoice) return;
    try {
      await updatePayment.mutateAsync({
        id: selectedInvoice.id,
        request: {
          payment_clearing_date: formData.payment_clearing_date,
          sap_clearing_doc_no: formData.sap_clearing_doc_no || undefined,
        },
      });
      setShowPaymentDialog(false);
      setSelectedInvoice(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Payment updated successfully',
        life: 3000,
      });
    } catch (error: any) {
      const rawDetail = error.response?.data?.detail;
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: typeof rawDetail === 'string' ? rawDetail : 'Failed to update payment',
        life: 5000,
      });
      setShowPaymentDialog(false);
      setSelectedInvoice(null);
    }
  }, [selectedInvoice, updatePayment]);

  const handleSettleConfirm = useCallback(async () => {
    if (!selectedInvoice) return;
    try {
      await markSettled.mutateAsync(selectedInvoice.id);
      setShowSettleDialog(false);
      setSelectedInvoice(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Invoice marked as Settled',
        life: 3000,
      });
    } catch (error: any) {
      const rawDetail = error.response?.data?.detail;
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: typeof rawDetail === 'string' ? rawDetail : 'Failed to mark invoice as settled',
        life: 5000,
      });
      setShowSettleDialog(false);
      setSelectedInvoice(null);
    }
  }, [selectedInvoice, markSettled]);

  const handleOpenPayment = (invoice: Invoice) => {
    setSelectedInvoice(invoice);
    setShowPaymentDialog(true);
  };

  const handleOpenSettle = (invoice: Invoice) => {
    setSelectedInvoice(invoice);
    setShowSettleDialog(true);
  };

  const handleOpenEligibility = (invoice: Invoice) => {
    setSelectedInvoice(invoice);
    setShowEligibilityPanel(true);
  };

  const handleOpenLines = (invoice: Invoice) => {
    setSelectedInvoice(invoice);
    setShowLinesDialog(true);
  };

  // ─── Column templates ───────────────────────────────────────────────────────
  const statusBodyTemplate = (rowData: Invoice) => {
    const severityMap: Record<string, 'info' | 'success' | 'warning'> = {
      'Open': 'info',
      'Payment Cleared': 'warning',
      'Settled': 'success',
    };
    return (
      <Tag
        value={rowData.status}
        severity={severityMap[rowData.status] ?? 'info'}
      />
    );
  };

  const dateBodyTemplate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    return dateStr;
  };

  const amountBodyTemplate = (amount: number | null) => {
    if (amount === null || amount === undefined) return '—';
    return amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const actionsBodyTemplate = (rowData: Invoice) => {
    return (
      <div className="flex gap-1">
        <Button
          icon="pi pi-list"
          severity="secondary"
          text
          rounded
          size="small"
          onClick={() => handleOpenLines(rowData)}
          aria-label={`View line items for invoice ${rowData.invoice_number}`}
          tooltip="View Line Items"
          tooltipOptions={{ position: 'top' }}
        />
        <Button
          icon="pi pi-credit-card"
          severity="info"
          text
          rounded
          size="small"
          onClick={() => handleOpenPayment(rowData)}
          disabled={rowData.status !== 'Open'}
          aria-label={`Update payment for invoice ${rowData.invoice_number}`}
          tooltip="Update Payment"
          tooltipOptions={{ position: 'top' }}
        />
        <Button
          icon="pi pi-check-square"
          severity="success"
          text
          rounded
          size="small"
          onClick={() => handleOpenSettle(rowData)}
          disabled={rowData.status !== 'Payment Cleared'}
          aria-label={`Mark settled for invoice ${rowData.invoice_number}`}
          tooltip="Mark Settled"
          tooltipOptions={{ position: 'top' }}
        />
        <Button
          icon="pi pi-verified"
          severity="warning"
          text
          rounded
          size="small"
          onClick={() => handleOpenEligibility(rowData)}
          aria-label={`Check eligibility for invoice ${rowData.invoice_number}`}
          tooltip="Check Eligibility"
          tooltipOptions={{ position: 'top' }}
        />
      </div>
    );
  };

  // ─── Column filter templates ────────────────────────────────────────────────
  const invoiceNumberFilterTemplate = () => (
    <InputText
      value={filterInvoiceNumber}
      onChange={(e) => { setFilterInvoiceNumber(e.target.value); setPage(0); }}
      placeholder="Search..."
      className="w-full"
      aria-label="Filter by Invoice Number"
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
        label="New Invoice"
        icon="pi pi-plus"
        onClick={() => setShowCreateDialog(true)}
        aria-label="Create new invoice"
      />
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Invoice Management</h2>
        <p className="text-600 mt-1 mb-0">Manage invoice records, payments, and settlements</p>
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
            emptyMessage="No invoices found."
            stripedRows
            size="small"
            aria-label="Invoice list table"
            filterDisplay="row"
          >
            <Column
              field="invoice_number"
              header="Invoice Number"
              sortable
              filter
              showFilterMenu={false}
              filterElement={invoiceNumberFilterTemplate}
              style={{ minWidth: '150px' }}
            />
            <Column
              field="invoice_date"
              header="Invoice Date"
              sortable
              body={(rowData: Invoice) => dateBodyTemplate(rowData.invoice_date)}
              style={{ minWidth: '120px' }}
            />
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
              field="customer_name"
              header="Customer Name"
              sortable
              filter
              showFilterMenu={false}
              filterElement={customerNameFilterTemplate}
              style={{ minWidth: '160px' }}
            />
            <Column
              field="bill_amount_excl_gst"
              header="Bill Amount"
              sortable
              body={(rowData: Invoice) => amountBodyTemplate(rowData.bill_amount_excl_gst)}
              style={{ minWidth: '130px' }}
            />
            <Column
              field="due_date"
              header="Due Date"
              sortable
              body={(rowData: Invoice) => dateBodyTemplate(rowData.due_date)}
              style={{ minWidth: '120px' }}
            />
            <Column
              field="payment_clearing_date"
              header="Payment Clearing Date"
              sortable
              body={(rowData: Invoice) => dateBodyTemplate(rowData.payment_clearing_date)}
              style={{ minWidth: '160px' }}
            />
            <Column
              field="status"
              header="Invoice Status"
              sortable
              body={statusBodyTemplate}
              style={{ minWidth: '140px' }}
            />
            <Column
              header="Actions"
              body={actionsBodyTemplate}
              style={{ minWidth: '175px' }}
              frozen
              alignFrozen="right"
            />
          </DataTable>
      </div>

      {/* Create Invoice Dialog */}
      <InvoiceForm
        visible={showCreateDialog}
        onHide={() => setShowCreateDialog(false)}
        onSubmit={handleCreateSubmit}
        loading={createInvoice.isPending}
      />

      {/* Payment Update Dialog */}
      <PaymentUpdateDialog
        visible={showPaymentDialog}
        onHide={() => { setShowPaymentDialog(false); setSelectedInvoice(null); }}
        onSubmit={handlePaymentSubmit}
        loading={updatePayment.isPending}
      />

      {/* Settle Confirmation Dialog */}
      <SettleConfirmDialog
        visible={showSettleDialog}
        onHide={() => { setShowSettleDialog(false); setSelectedInvoice(null); }}
        onConfirm={handleSettleConfirm}
        loading={markSettled.isPending}
      />

      {/* Eligibility Panel */}
      {selectedInvoice && (
        <EligibilityPanel
          invoiceId={selectedInvoice.id}
          visible={showEligibilityPanel}
          onHide={() => { setShowEligibilityPanel(false); setSelectedInvoice(null); }}
        />
      )}

      {/* Invoice Line Items Dialog */}
      <InvoiceLineViewDialog
        invoice={selectedInvoice}
        visible={showLinesDialog}
        onHide={() => { setShowLinesDialog(false); setSelectedInvoice(null); }}
      />
    </div>
  );
};
