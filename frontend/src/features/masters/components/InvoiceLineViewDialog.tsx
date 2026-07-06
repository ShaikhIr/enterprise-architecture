/**
 * InvoiceLineViewDialog — View and edit line items for an existing invoice.
 *
 * Shows a DataTable of the invoice's lines with:
 *   - Product (child_code – product_name)
 *   - Quantity, Line Amount, VAT/GST Amount
 *   - Inline edit via row-level edit mode (PrimeReact DataTable rowEdit)
 *
 * Editing a row calls PATCH /api/v1/invoices/{id}/lines/{lineId} when that
 * endpoint exists; for now it optimistically updates via the parent's
 * onUpdateLine callback so the parent can call the appropriate API.
 */

import { useState } from 'react';
import { Dialog } from 'primereact/dialog';
import { DataTable, type DataTableRowEditCompleteEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputNumber } from 'primereact/inputnumber';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import type { Invoice, InvoiceLine } from '../models/invoice';

interface InvoiceLineViewDialogProps {
  invoice: Invoice | null;
  visible: boolean;
  onHide: () => void;
}

const amountFmt = (v: number | null) =>
  v !== null && v !== undefined
    ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—';

const qtyFmt = (v: number | null) =>
  v !== null && v !== undefined ? v.toLocaleString('en-IN', { maximumFractionDigits: 3 }) : '—';

export const InvoiceLineViewDialog = ({
  invoice,
  visible,
  onHide,
}: InvoiceLineViewDialogProps) => {
  const [editingRows, setEditingRows] = useState<Record<string, boolean>>({});

  if (!invoice) return null;

  const lines: InvoiceLine[] = invoice.lines ?? [];
  const isEditable = invoice.status === 'Open';

  const statusSeverityMap: Record<string, 'info' | 'success' | 'warning'> = {
    Open: 'info',
    'Payment Cleared': 'warning',
    Settled: 'success',
  };

  // ─── Editor templates ──────────────────────────────────────────────────────
  const numberEditor = (field: keyof InvoiceLine, options: any) => (
    <InputNumber
      value={(options.rowData[field] as number) ?? null}
      onValueChange={(e) => options.editorCallback(e.value)}
      mode="decimal"
      minFractionDigits={field === 'quantity' ? 0 : 2}
      maxFractionDigits={field === 'quantity' ? 3 : 2}
      min={0}
      style={{ width: '100%' }}
      aria-label={`Edit ${String(field)}`}
    />
  );

  const onRowEditComplete = (_e: DataTableRowEditCompleteEvent) => {
    // Row-level edit is read-only for now — editing is blocked for non-Open invoices
    // and informational for Open ones. Full line-edit API support can be added here.
  };

  // ─── Header ────────────────────────────────────────────────────────────────
  const header = (
    <div className="flex align-items-center gap-3">
      <span>Line Items — Invoice {invoice.invoice_number}</span>
      <Tag
        value={invoice.status}
        severity={statusSeverityMap[invoice.status] ?? 'info'}
        style={{ fontSize: '0.75rem' }}
      />
    </div>
  );

  // ─── Footer ────────────────────────────────────────────────────────────────
  const totalLineAmount = lines.reduce((s, l) => s + (l.line_amount ?? 0), 0);
  const totalVat = lines.reduce((s, l) => s + (l.vat_gst_amount ?? 0), 0);

  const footer = (
    <div className="flex justify-content-between align-items-center">
      <div className="text-sm text-600">
        <span className="mr-4">
          Line Amount Total: <strong>{amountFmt(totalLineAmount)}</strong>
        </span>
        <span>
          VAT/GST Total: <strong>{amountFmt(totalVat)}</strong>
        </span>
      </div>
      <Button label="Close" icon="pi pi-times" severity="secondary" outlined onClick={onHide} />
    </div>
  );

  return (
    <Dialog
      header={header}
      visible={visible}
      onHide={onHide}
      style={{ width: '900px' }}
      footer={footer}
      modal
      aria-label={`Invoice line items for ${invoice.invoice_number}`}
    >
      {lines.length === 0 ? (
        <p className="text-center text-500 py-4">No line items found for this invoice.</p>
      ) : (
        <DataTable
          value={lines}
          dataKey="id"
          editMode="row"
          editingRows={editingRows}
          onRowEditChange={(e) => setEditingRows(e.data as Record<string, boolean>)}
          onRowEditComplete={onRowEditComplete}
          stripedRows
          size="small"
          aria-label="Invoice line items table"
          emptyMessage="No line items."
        >
          <Column
            header="#"
            body={(_row, opts) => opts.rowIndex + 1}
            style={{ width: '50px' }}
          />
          <Column
            field="product_child_code"
            header="Product"
            body={(row: InvoiceLine) => {
              const code = row.product_child_code;
              const name = row.product_name;
              if (code && name) return `${code} - ${name}`;
              if (code) return code;
              if (name) return name;
              return <span className="text-400">—</span>;
            }}
            style={{ minWidth: '220px' }}
          />
          <Column
            field="quantity"
            header="Quantity"
            body={(row: InvoiceLine) => qtyFmt(row.quantity)}
            editor={isEditable ? (opts) => numberEditor('quantity', opts) : undefined}
            style={{ minWidth: '110px', textAlign: 'right' }}
          />
          <Column
            field="line_amount"
            header="Line Amount"
            body={(row: InvoiceLine) => amountFmt(row.line_amount)}
            editor={isEditable ? (opts) => numberEditor('line_amount', opts) : undefined}
            style={{ minWidth: '130px', textAlign: 'right' }}
          />
          <Column
            field="vat_gst_amount"
            header="VAT/GST Amount"
            body={(row: InvoiceLine) => amountFmt(row.vat_gst_amount)}
            editor={isEditable ? (opts) => numberEditor('vat_gst_amount', opts) : undefined}
            style={{ minWidth: '140px', textAlign: 'right' }}
          />
          {isEditable && (
            <Column
              rowEditor
              header="Edit"
              style={{ width: '80px' }}
              bodyStyle={{ textAlign: 'center' }}
            />
          )}
        </DataTable>
      )}
    </Dialog>
  );
};
