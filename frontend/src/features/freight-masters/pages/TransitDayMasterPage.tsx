/**
 * Transit Day Master page.
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

interface TransitDayItem {
  id: string;
  country_name: string;
  country_code: string | null;
  customer_clearance: number | null;
  transit_days_for_air: number | null;
  container_load_for_sea: number | null;
  test_days: number | null;
  is_active: boolean;
}

const emptyForm = { country_name: '', country_code: '', customer_clearance: null as number | null, transit_days_for_air: null as number | null, container_load_for_sea: null as number | null, test_days: null as number | null };

export const TransitDayMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [items, setItems] = useState<TransitDayItem[]>([]);
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
    try { const { data } = await apiClient.get<TransitDayItem[]>('/masters/transit-days', { params: { include_inactive: true } }); setItems(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load', life: 5000 }); }
    finally { setLoading(false); }
  };

  const openNew = () => { setEditingId(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (item: TransitDayItem) => { setEditingId(item.id); setForm({ country_name: item.country_name, country_code: item.country_code || '', customer_clearance: item.customer_clearance, transit_days_for_air: item.transit_days_for_air, container_load_for_sea: item.container_load_for_sea, test_days: item.test_days }); setShowDialog(true); };

  const onSave = async () => {
    if (!form.country_name.trim()) return;
    setSaving(true);
    try {
      const payload = { ...form, country_code: form.country_code || null };
      if (editingId) await apiClient.put(`/masters/transit-days/${editingId}`, payload);
      else await apiClient.post('/masters/transit-days', payload);
      toast.current?.show({ severity: 'success', summary: 'Saved', life: 3000 });
      setShowDialog(false); load();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
    finally { setSaving(false); }
  };

  const confirmDelete = (item: TransitDayItem) => {
    confirmDialog({ message: `Deactivate "${item.country_name}"?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger',
      accept: async () => { try { await apiClient.delete(`/masters/transit-days/${item.id}`); toast.current?.show({ severity: 'success', summary: 'Deactivated', life: 3000 }); load(); } catch { toast.current?.show({ severity: 'error', summary: 'Error', life: 5000 }); } },
    });
  };

  const downloadTemplate = async () => {
    const { data } = await apiClient.get('/masters/transit-days-template', { responseType: 'blob' });
    const url = window.URL.createObjectURL(data as Blob);
    const a = document.createElement('a'); a.href = url; a.download = 'transit_days_template.xlsx'; a.click();
    window.URL.revokeObjectURL(url);
  };

  const doImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try {
      const fd = new FormData(); fd.append('file', importFile);
      const { data } = await apiClient.post('/masters/transit-days-import', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message, life: 5000 });
      setShowImport(false); setImportFile(null); load();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Import Failed', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
    finally { setImporting(false); }
  };

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="flex justify-content-between align-items-center mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Transit Day Master</h2>
        <div className="flex gap-2">
          <Button label="Import Excel" icon="pi pi-file-excel" severity="success" onClick={() => setShowImport(true)} />
          <Button label="Add" icon="pi pi-plus" onClick={openNew} />
        </div>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <DataTable value={items} loading={loading} stripedRows paginator rows={15} emptyMessage="No records" size="small" filterDisplay="row">
          <Column field="country_name" header="Country" sortable filter filterPlaceholder="Filter" />
          <Column field="country_code" header="Code" sortable filter filterPlaceholder="Filter" body={(r: TransitDayItem) => r.country_code || '—'} />
          <Column field="customer_clearance" header="Cust. Clearance" body={(r: TransitDayItem) => r.customer_clearance ?? '—'} />
          <Column field="transit_days_for_air" header="Transit (Air)" body={(r: TransitDayItem) => r.transit_days_for_air ?? '—'} />
          <Column field="container_load_for_sea" header="Transit (Sea)" body={(r: TransitDayItem) => r.container_load_for_sea ?? '—'} />
          <Column field="test_days" header="Test Days" body={(r: TransitDayItem) => r.test_days ?? '—'} />
          <Column header="Status" body={(r: TransitDayItem) => <Tag value={r.is_active ? 'Active' : 'Inactive'} severity={r.is_active ? 'success' : 'secondary'} />} style={{ width: '7rem' }} />
          <Column header="Actions" style={{ width: '8rem' }} body={(r: TransitDayItem) => (
            <div className="flex align-items-center gap-2">
              <Button icon="pi pi-pencil" rounded outlined severity="info" size="small" onClick={() => openEdit(r)} style={{ width: '2rem', height: '2rem' }} />
              {r.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => confirmDelete(r)} style={{ width: '2rem', height: '2rem' }} />}
            </div>
          )} />
        </DataTable>
      </div>

      {/* CRUD Dialog */}
      <Dialog header={editingId ? 'Edit' : 'Add New'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '550px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={onSave} disabled={!form.country_name.trim() || saving} loading={saving} /></div>}
      >
        <div className="mt-3" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="flex flex-column gap-2"><label className="font-medium">Country *</label><InputText value={form.country_name} onChange={(e) => setForm({ ...form, country_name: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Country Code</label><InputText value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value })} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Customer Clearance</label><InputNumber value={form.customer_clearance} onValueChange={(e) => setForm({ ...form, customer_clearance: e.value ?? null })} useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Transit Days (Air)</label><InputNumber value={form.transit_days_for_air} onValueChange={(e) => setForm({ ...form, transit_days_for_air: e.value ?? null })} useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Transit Days (Sea)</label><InputNumber value={form.container_load_for_sea} onValueChange={(e) => setForm({ ...form, container_load_for_sea: e.value ?? null })} useGrouping={false} /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Test Days</label><InputNumber value={form.test_days} onValueChange={(e) => setForm({ ...form, test_days: e.value ?? null })} useGrouping={false} /></div>
        </div>
      </Dialog>

      {/* Import Dialog */}
      <Dialog header="Import Transit Days from Excel" visible={showImport} onHide={() => setShowImport(false)} style={{ width: '450px' }} modal closable={!importing}
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
