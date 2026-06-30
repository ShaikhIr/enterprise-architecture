/**
 * Currency Conversion Rate Master page.
 * Multi-field form: EXRT, From/To currency, Valid From, Exchange Rate, Ratio From/To.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { Calendar } from 'primereact/calendar';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { apiClient } from '@shared/services/apiClient';

interface ConversionItem {
  id: string;
  exrt: string | null;
  from_currency: string;
  to_currency: string;
  valid_from: string | null;
  exchange_rate: number | null;
  ratio_from: number | null;
  ratio_to: number | null;
  is_active: boolean;
}

const emptyForm = {
  exrt: '',
  from_currency: '',
  to_currency: '',
  valid_from: null as Date | null,
  exchange_rate: null as number | null,
  ratio_from: null as number | null,
  ratio_to: null as number | null,
};

export const CurrencyConversionPage = () => {
  const toast = useRef<Toast>(null);
  const [items, setItems] = useState<ConversionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<ConversionItem[]>('/masters/currency-conversions', { params: { include_inactive: true } });
      setItems(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load data', life: 5000 });
    } finally { setLoading(false); }
  };

  const openNew = () => { setEditingId(null); setForm(emptyForm); setShowDialog(true); };

  const openEdit = (item: ConversionItem) => {
    setEditingId(item.id);
    setForm({
      exrt: item.exrt || '',
      from_currency: item.from_currency,
      to_currency: item.to_currency,
      valid_from: item.valid_from ? new Date(item.valid_from) : null,
      exchange_rate: item.exchange_rate,
      ratio_from: item.ratio_from,
      ratio_to: item.ratio_to,
    });
    setShowDialog(true);
  };

  const onSave = async () => {
    if (!form.from_currency.trim() || !form.to_currency.trim()) return;
    setSaving(true);
    try {
      const payload = {
        exrt: form.exrt || null,
        from_currency: form.from_currency.trim(),
        to_currency: form.to_currency.trim(),
        valid_from: form.valid_from ? form.valid_from.toISOString() : null,
        exchange_rate: form.exchange_rate,
        ratio_from: form.ratio_from,
        ratio_to: form.ratio_to,
      };
      if (editingId) {
        await apiClient.put(`/masters/currency-conversions/${editingId}`, payload);
      } else {
        await apiClient.post('/masters/currency-conversions', payload);
      }
      toast.current?.show({ severity: 'success', summary: 'Saved', life: 3000 });
      setShowDialog(false);
      load();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Save failed', life: 5000 });
    } finally { setSaving(false); }
  };

  const confirmDelete = (item: ConversionItem) => {
    confirmDialog({
      message: `Deactivate ${item.from_currency} → ${item.to_currency}?`,
      header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await apiClient.delete(`/masters/currency-conversions/${item.id}`);
          toast.current?.show({ severity: 'success', summary: 'Deactivated', life: 3000 });
          load();
        } catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed', life: 5000 }); }
      },
    });
  };

  const confirmSapImport = () => {
    confirmDialog({
      message: 'Are you sure you want to import exchange rates from SAP? This will fetch the latest conversion rates.',
      header: 'Import from SAP',
      icon: 'pi pi-cloud-download',
      acceptLabel: 'Yes, Import',
      rejectLabel: 'Cancel',
      accept: async () => {
        toast.current?.show({ severity: 'info', summary: 'Importing...', detail: 'Fetching exchange rates from SAP', life: 5000 });
        try {
          const { data } = await apiClient.post('/masters/currency-conversions/import-sap', {});
          toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message, life: 5000 });
          load();
        } catch (e: any) {
          toast.current?.show({ severity: 'error', summary: 'Import Failed', detail: e.response?.data?.detail || 'Failed to import from SAP', life: 5000 });
        }
      },
    });
  };

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="flex justify-content-between align-items-center mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Currency Conversion Rate</h2>
        <div className="flex gap-2">
          <Button label="Import from SAP" icon="pi pi-cloud-download" outlined onClick={confirmSapImport} />
          <Button label="Add" icon="pi pi-plus" onClick={openNew} />
        </div>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <DataTable value={items} loading={loading} stripedRows paginator rows={15} emptyMessage="No records found" size="small" filterDisplay="row">
          <Column field="exrt" header="EXRT" sortable filter filterPlaceholder="Filter" />
          <Column field="from_currency" header="From" sortable filter filterPlaceholder="Filter" />
          <Column field="to_currency" header="To" sortable filter filterPlaceholder="Filter" />
          <Column field="valid_from" header="Valid From" body={(r: ConversionItem) => r.valid_from ? new Date(r.valid_from).toLocaleDateString() : '—'} />
          <Column field="exchange_rate" header="Rate" sortable filter filterPlaceholder="Filter" body={(r: ConversionItem) => r.exchange_rate ?? '—'} />
          <Column field="ratio_from" header="Ratio From" body={(r: ConversionItem) => r.ratio_from ?? '—'} />
          <Column field="ratio_to" header="Ratio To" body={(r: ConversionItem) => r.ratio_to ?? '—'} />
          <Column header="Status" body={(r: ConversionItem) => <Tag value={r.is_active ? 'Active' : 'Inactive'} severity={r.is_active ? 'success' : 'secondary'} />} style={{ width: '7rem' }} />
          <Column header="Actions" style={{ width: '8rem' }} body={(r: ConversionItem) => (
            <div className="flex align-items-center gap-2">
              <Button icon="pi pi-pencil" rounded outlined severity="info" size="small" onClick={() => openEdit(r)} style={{ width: '2rem', height: '2rem' }} />
              {r.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => confirmDelete(r)} style={{ width: '2rem', height: '2rem' }} />}
            </div>
          )} />
        </DataTable>
      </div>

      <Dialog header={editingId ? 'Edit' : 'Add New'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '550px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={onSave} disabled={!form.from_currency.trim() || !form.to_currency.trim() || saving} loading={saving} /></div>}
      >
        <div className="grid mt-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="flex flex-column gap-2"><label className="font-medium">EXRT</label><InputText value={form.exrt} onChange={(e) => setForm({ ...form, exrt: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Valid From</label><Calendar value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.value as Date | null })} dateFormat="dd/mm/yy" showIcon /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">From Currency *</label><InputText value={form.from_currency} onChange={(e) => setForm({ ...form, from_currency: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">To Currency *</label><InputText value={form.to_currency} onChange={(e) => setForm({ ...form, to_currency: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Exchange Rate</label><InputNumber value={form.exchange_rate} onValueChange={(e) => setForm({ ...form, exchange_rate: e.value ?? null })} mode="decimal" minFractionDigits={2} maxFractionDigits={6} useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Ratio From</label><InputNumber value={form.ratio_from} onValueChange={(e) => setForm({ ...form, ratio_from: e.value ?? null })} useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Ratio To</label><InputNumber value={form.ratio_to} onValueChange={(e) => setForm({ ...form, ratio_to: e.value ?? null })} useGrouping={false} /></div>
        </div>
      </Dialog>
    </div>
  );
};
