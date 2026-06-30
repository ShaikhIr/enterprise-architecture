/**
 * Sea CBM Master page — CRUD with Excel import.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { SeaCbm, seaCbmService } from '../services/freightMasterService';

interface CbmForm {
  slab_name: string;
  from_cbm: number | null;
  to_cbm: number | null;
  type: string;
  total_count: number | null;
}
const emptyForm: CbmForm = { slab_name: '', from_cbm: null, to_cbm: null, type: '', total_count: null };

export const SeaCbmMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<SeaCbm[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<SeaCbm | null>(null);
  const [form, setForm] = useState<CbmForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await seaCbmService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load Sea CBM Masters', life: 5000 }); }
    finally { setLoading(false); }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: SeaCbm) => { setEditingRecord(r); setForm({ slab_name: r.slab_name || '', from_cbm: r.from_cbm, to_cbm: r.to_cbm, type: r.type || '', total_count: r.total_count }); setShowDialog(true); };

  const handleSave = async () => {
    if (form.from_cbm === null || form.to_cbm === null) { toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'From CBM and To CBM are required', life: 3000 }); return; }
    setSubmitting(true);
    try {
      const payload = { slab_name: form.slab_name || null, from_cbm: form.from_cbm, to_cbm: form.to_cbm, type: form.type || null, total_count: form.total_count };
      if (editingRecord) { await seaCbmService.update(editingRecord.id, payload); toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Sea CBM updated', life: 3000 }); }
      else { await seaCbmService.create(payload as any); toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Sea CBM created', life: 3000 }); }
      setShowDialog(false); loadData();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 }); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = (r: SeaCbm) => { confirmDialog({ message: `Deactivate "${r.slab_name || r.from_cbm + '-' + r.to_cbm}"?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) }); };
  const handleDelete = async (id: string) => {
    try { await seaCbmService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Sea CBM deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const handleExcelImport = async () => {
    if (!importFile) return; setImporting(true);
    try { const { data } = await seaCbmService.importExcel(importFile); toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message || 'Done', life: 5000 }); setShowImportDialog(false); setImportFile(null); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Import failed', life: 5000 }); }
    finally { setImporting(false); }
  };
  const downloadTemplate = async () => {
    try { const response = await seaCbmService.downloadTemplate(); const url = window.URL.createObjectURL(new Blob([response.data])); const a = document.createElement('a'); a.href = url; a.download = 'sea_cbm_master_template.xlsx'; a.click(); window.URL.revokeObjectURL(url); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Template download failed', life: 5000 }); }
  };

  const statusTemplate = (row: SeaCbm) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const actionsTemplate = (row: SeaCbm) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Sea CBM Master</h2>
        <p className="text-600 mt-1 mb-0">Manage sea cubic metre slab definitions</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Sea CBM" icon="pi pi-plus" onClick={openNew} />
            <Button label="Import Excel" icon="pi pi-file-excel" severity="success" outlined onClick={() => setShowImportDialog(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No Sea CBM records found">
          <Column field="slab_name" header="Slab Name" sortable filter filterPlaceholder="Search..." />
          <Column field="from_cbm" header="From CBM" sortable />
          <Column field="to_cbm" header="To CBM" sortable />
          <Column field="type" header="Type" sortable filter />
          <Column field="total_count" header="Total Count" sortable />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      <Dialog header={editingRecord ? 'Edit Sea CBM' : 'New Sea CBM'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '500px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2"><label className="font-medium">Slab Name</label><InputText value={form.slab_name} onChange={(e) => setForm({ ...form, slab_name: e.target.value })} className="w-full" /></div>
          <div className="grid">
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">From CBM *</label><InputNumber value={form.from_cbm} onValueChange={(e) => setForm({ ...form, from_cbm: e.value ?? null })} className="w-full" /></div>
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">To CBM *</label><InputNumber value={form.to_cbm} onValueChange={(e) => setForm({ ...form, to_cbm: e.value ?? null })} className="w-full" /></div>
          </div>
          <div className="flex flex-column gap-2"><label className="font-medium">Type</label><InputText value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Total Count</label><InputNumber value={form.total_count} onValueChange={(e) => setForm({ ...form, total_count: e.value ?? null })} className="w-full" /></div>
        </div>
      </Dialog>

      <Dialog header="Import Sea CBM from Excel" visible={showImportDialog} onHide={() => { if (!importing) setShowImportDialog(false); }} style={{ width: '450px' }} modal closable={!importing}
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowImportDialog(false)} disabled={importing} /><Button label="Import" icon="pi pi-upload" onClick={handleExcelImport} disabled={!importFile || importing} loading={importing} /></div>}>
        {!importing ? (
          <div className="flex flex-column gap-3">
            <a onClick={downloadTemplate} style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.85rem', cursor: 'pointer' }}><i className="pi pi-download" style={{ marginRight: '0.3rem' }}></i>Download Template</a>
            <div className="flex flex-column gap-2"><label className="font-medium">Select Excel File (.xlsx)</label><input type="file" accept=".xlsx,.xls" onChange={(e) => setImportFile(e.target.files?.[0] || null)} /></div>
          </div>
        ) : (<div className="flex flex-column align-items-center gap-3 py-4"><i className="pi pi-spin pi-spinner" style={{ fontSize: '2rem', color: '#2563eb' }}></i><p className="font-medium m-0">Importing...</p></div>)}
      </Dialog>
    </div>
  );
};
