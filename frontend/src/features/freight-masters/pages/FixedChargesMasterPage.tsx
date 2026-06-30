/**
 * Fixed Charges Master page.
 * Multi-field CRUD with Excel import support.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { apiClient } from '@shared/services/apiClient';

interface FixedChargesItem {
  id: string;
  mode_of_shipment: string | null;
  pallet_name: string | null;
  document_charges: number | null;
  shrink_wrap_charges: number | null;
  unloading_charges: number | null;
  pallet_charges: number | null;
  data_logger_charges: number | null;
  blanket_charges: number | null;
  is_active: boolean;
}

const emptyForm = { mode_of_shipment: '', pallet_name: '', document_charges: null as number | null, shrink_wrap_charges: null as number | null, unloading_charges: null as number | null, pallet_charges: null as number | null, data_logger_charges: null as number | null, blanket_charges: null as number | null };

export const FixedChargesMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [items, setItems] = useState<FixedChargesItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { const { data } = await apiClient.get<FixedChargesItem[]>('/masters/fixed-charges', { params: { include_inactive: true } }); setItems(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load', life: 5000 }); }
    finally { setLoading(false); }
  };

  const openNew = () => { setEditingId(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (item: FixedChargesItem) => {
    setEditingId(item.id);
    setForm({ mode_of_shipment: item.mode_of_shipment || '', pallet_name: item.pallet_name || '', document_charges: item.document_charges, shrink_wrap_charges: item.shrink_wrap_charges, unloading_charges: item.unloading_charges, pallet_charges: item.pallet_charges, data_logger_charges: item.data_logger_charges, blanket_charges: item.blanket_charges });
    setShowDialog(true);
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const payload = { ...form, mode_of_shipment: form.mode_of_shipment || null, pallet_name: form.pallet_name || null };
      if (editingId) await apiClient.put(`/masters/fixed-charges/${editingId}`, payload);
      else await apiClient.post('/masters/fixed-charges', payload);
      toast.current?.show({ severity: 'success', summary: 'Saved', life: 3000 });
      setShowDialog(false); load();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
    finally { setSaving(false); }
  };

  const confirmDelete = (item: FixedChargesItem) => {
    confirmDialog({ message: 'Deactivate this record?', header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger',
      accept: async () => { try { await apiClient.delete(`/masters/fixed-charges/${item.id}`); toast.current?.show({ severity: 'success', summary: 'Deactivated', life: 3000 }); load(); } catch { toast.current?.show({ severity: 'error', summary: 'Error', life: 5000 }); } },
    });
  };

  const downloadTemplate = async () => {
    const { data } = await apiClient.get('/masters/fixed-charges-template', { responseType: 'blob' });
    const url = window.URL.createObjectURL(data as Blob);
    const a = document.createElement('a'); a.href = url; a.download = 'fixed_charges_template.xlsx'; a.click();
    window.URL.revokeObjectURL(url);
  };

  const doImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try {
      const fd = new FormData(); fd.append('file', importFile);
      const { data } = await apiClient.post('/masters/fixed-charges-import', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message, life: 5000 });
      setShowImport(false); setImportFile(null); load();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Import Failed', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
    finally { setImporting(false); }
  };

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="flex justify-content-between align-items-center mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Fixed Charges Master</h2>
        <div className="flex gap-2">
          <Button label="Import Excel" icon="pi pi-file-excel" severity="success" onClick={() => setShowImport(true)} />
          <Button label="Add" icon="pi pi-plus" onClick={openNew} />
        </div>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <DataTable value={items} loading={loading} stripedRows paginator rows={15} emptyMessage="No records" size="small" filterDisplay="row">
          <Column field="mode_of_shipment" header="MOS" sortable filter filterPlaceholder="Filter" body={(r: FixedChargesItem) => r.mode_of_shipment || '—'} />
          <Column field="pallet_name" header="Pallet" sortable filter filterPlaceholder="Filter" body={(r: FixedChargesItem) => r.pallet_name || '—'} />
          <Column field="document_charges" header="Document" body={(r: FixedChargesItem) => r.document_charges ?? '—'} />
          <Column field="shrink_wrap_charges" header="Shrink Wrap" body={(r: FixedChargesItem) => r.shrink_wrap_charges ?? '—'} />
          <Column field="unloading_charges" header="Unloading" body={(r: FixedChargesItem) => r.unloading_charges ?? '—'} />
          <Column field="pallet_charges" header="Pallet" body={(r: FixedChargesItem) => r.pallet_charges ?? '—'} />
          <Column field="data_logger_charges" header="Data Logger" body={(r: FixedChargesItem) => r.data_logger_charges ?? '—'} />
          <Column field="blanket_charges" header="Blanket" body={(r: FixedChargesItem) => r.blanket_charges ?? '—'} />
          <Column header="Status" body={(r: FixedChargesItem) => <Tag value={r.is_active ? 'Active' : 'Inactive'} severity={r.is_active ? 'success' : 'secondary'} />} style={{ width: '6rem' }} />
          <Column header="Actions" style={{ width: '8rem' }} body={(r: FixedChargesItem) => (
            <div className="flex align-items-center gap-2">
              <Button icon="pi pi-pencil" rounded outlined severity="info" size="small" onClick={() => openEdit(r)} style={{ width: '2rem', height: '2rem' }} />
              {r.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => confirmDelete(r)} style={{ width: '2rem', height: '2rem' }} />}
            </div>
          )} />
        </DataTable>
      </div>

      {/* CRUD Dialog */}
      <Dialog header={editingId ? 'Edit' : 'Add New'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '600px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={onSave} disabled={saving} loading={saving} /></div>}
      >
        <div className="mt-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="flex flex-column gap-2"><label className="font-medium">Mode of Shipment</label><InputText value={form.mode_of_shipment} onChange={(e) => setForm({ ...form, mode_of_shipment: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Pallet Name</label><InputText value={form.pallet_name} onChange={(e) => setForm({ ...form, pallet_name: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Document Charges</label><InputNumber value={form.document_charges} onValueChange={(e) => setForm({ ...form, document_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Shrink Wrap Charges</label><InputNumber value={form.shrink_wrap_charges} onValueChange={(e) => setForm({ ...form, shrink_wrap_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Unloading Charges</label><InputNumber value={form.unloading_charges} onValueChange={(e) => setForm({ ...form, unloading_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Pallet Charges</label><InputNumber value={form.pallet_charges} onValueChange={(e) => setForm({ ...form, pallet_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Data Logger Charges</label><InputNumber value={form.data_logger_charges} onValueChange={(e) => setForm({ ...form, data_logger_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Blanket Charges</label><InputNumber value={form.blanket_charges} onValueChange={(e) => setForm({ ...form, blanket_charges: e.value ?? null })} mode="decimal" useGrouping={false} /></div>
        </div>
      </Dialog>

      {/* Import Dialog */}
      <Dialog header="Import Fixed Charges from Excel" visible={showImport} onHide={() => setShowImport(false)} style={{ width: '450px' }} modal closable={!importing}
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowImport(false)} disabled={importing} /><Button label="Import" icon="pi pi-upload" onClick={doImport} disabled={!importFile || importing} loading={importing} /></div>}
      >
        <div className="flex flex-column gap-3 mt-2">
          <a onClick={downloadTemplate} className="cursor-pointer text-primary no-underline text-sm"><i className="pi pi-download mr-1" />Download Template</a>
          <div><label className="font-medium block mb-2">Select Excel File</label><input type="file" accept=".xlsx,.xls" onChange={(e) => setImportFile(e.target.files?.[0] || null)} /></div>
        </div>
      </Dialog>
    </div>
  );
};
