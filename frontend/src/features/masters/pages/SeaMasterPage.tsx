/**
 * Sea Master page — CRUD with rates management and Excel import.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { Calendar } from 'primereact/calendar';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import {
  SeaMaster, Country, Rate, seaMasterService, countryService,
} from '../services/freightMasterService';

interface SeaForm {
  to_country_id: string;
  product_type: string;
  slab_name: string;
  currency: string;
}
const emptyForm: SeaForm = { to_country_id: '', product_type: '', slab_name: '', currency: '' };

export const SeaMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<SeaMaster[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showRateDialog, setShowRateDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<SeaMaster | null>(null);
  const [selectedMaster, setSelectedMaster] = useState<SeaMaster | null>(null);
  const [form, setForm] = useState<SeaForm>(emptyForm);
  const [rateForm, setRateForm] = useState({ rate: null as number | null, valid_from: null as Date | null, valid_till: null as Date | null });
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [expandedRows, setExpandedRows] = useState<any>(null);

  useEffect(() => { loadData(); loadCountries(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await seaMasterService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load Sea Masters', life: 5000 }); }
    finally { setLoading(false); }
  };
  const loadCountries = async () => { try { const { data } = await countryService.list(); setCountries(data); } catch { /* silent */ } };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: SeaMaster) => {
    setEditingRecord(r);
    setForm({ to_country_id: r.to_country_id, product_type: r.product_type || '', slab_name: r.slab_name || '', currency: r.currency || '' });
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.to_country_id) { toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Country is required', life: 3000 }); return; }
    setSubmitting(true);
    try {
      const payload = { to_country_id: form.to_country_id, product_type: form.product_type || undefined, slab_name: form.slab_name || undefined, currency: form.currency || undefined };
      if (editingRecord) { await seaMasterService.update(editingRecord.id, payload); toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Sea Master updated', life: 3000 }); }
      else { await seaMasterService.create(payload); toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Sea Master created', life: 3000 }); }
      setShowDialog(false); loadData();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 }); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = (r: SeaMaster) => { confirmDialog({ message: `Deactivate Sea Master for ${r.country_name}?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) }); };
  const handleDelete = async (id: string) => {
    try { await seaMasterService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Sea Master deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const openRateDialog = (r: SeaMaster) => { setSelectedMaster(r); setRateForm({ rate: null, valid_from: null, valid_till: null }); setShowRateDialog(true); };
  const handleAddRate = async () => {
    if (!selectedMaster || !rateForm.rate || !rateForm.valid_from || !rateForm.valid_till) { toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'All rate fields required', life: 3000 }); return; }
    try { await seaMasterService.addRate(selectedMaster.id, { rate: rateForm.rate, valid_from: rateForm.valid_from.toISOString(), valid_till: rateForm.valid_till.toISOString() }); toast.current?.show({ severity: 'success', summary: 'Added', detail: 'Rate added', life: 3000 }); setShowRateDialog(false); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };
  const handleDeleteRate = async (rateId: string) => {
    try { await seaMasterService.deleteRate(rateId); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Rate deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const handleExcelImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try { const { data } = await seaMasterService.importExcel(importFile); toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message || 'Done', life: 5000 }); setShowImportDialog(false); setImportFile(null); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Import failed', life: 5000 }); }
    finally { setImporting(false); }
  };
  const downloadTemplate = async () => {
    try { const response = await seaMasterService.downloadTemplate(); const url = window.URL.createObjectURL(new Blob([response.data])); const a = document.createElement('a'); a.href = url; a.download = 'sea_master_template.xlsx'; a.click(); window.URL.revokeObjectURL(url); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template', life: 5000 }); }
  };

  const statusTemplate = (row: SeaMaster) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const ratesTemplate = (row: SeaMaster) => { const ar = (row.rates || []).filter(r => r.is_active); const firstRate = ar[0]; return <span>{firstRate ? `${firstRate.rate}` : '—'}</span>; };
  const actionsTemplate = (row: SeaMaster) => (
    <div className="flex gap-1">
      <Button icon="pi pi-plus-circle" rounded outlined size="small" tooltip="Add Rate" onClick={() => openRateDialog(row)} />
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );
  const rowExpansionTemplate = (row: SeaMaster) => {
    const activeRates = (row.rates || []).filter(r => r.is_active);
    if (activeRates.length === 0) return <p className="m-2 text-600">No active rates</p>;
    return (
      <div className="p-3">
        <DataTable value={activeRates} size="small">
          <Column field="rate" header="Rate" />
          <Column field="valid_from" header="Valid From" body={(r: Rate) => r.valid_from ? new Date(r.valid_from).toLocaleDateString() : '—'} />
          <Column field="valid_till" header="Valid Till" body={(r: Rate) => r.valid_till ? new Date(r.valid_till).toLocaleDateString() : '—'} />
          <Column header="" body={(r: Rate) => <Button icon="pi pi-times" rounded text severity="danger" size="small" onClick={() => handleDeleteRate(r.id)} />} style={{ width: '4rem' }} />
        </DataTable>
      </div>
    );
  };

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Sea Master</h2>
        <p className="text-600 mt-1 mb-0">Manage sea freight rates by country, product type, and currency</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Sea Master" icon="pi pi-plus" onClick={openNew} />
            <Button label="Import Excel" icon="pi pi-file-excel" severity="success" outlined onClick={() => setShowImportDialog(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} dataKey="id" expandedRows={expandedRows} onRowToggle={(e) => setExpandedRows(e.data)} rowExpansionTemplate={rowExpansionTemplate} emptyMessage="No sea masters found">
          <Column expander style={{ width: '3rem' }} />
          <Column field="country_name" header="Country Name" sortable filter filterPlaceholder="Search..." />
          <Column field="country_code" header="Country Code" sortable filter />
          <Column field="product_type" header="Product Type" sortable filter />
          <Column field="slab_name" header="Slab Name" sortable />
          <Column field="currency" header="Currency" sortable />
          <Column header="Rates" body={ratesTemplate} />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '10rem' }} />
        </DataTable>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog header={editingRecord ? 'Edit Sea Master' : 'New Sea Master'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '500px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2"><label className="font-medium">Country *</label><Dropdown value={form.to_country_id} options={countries} optionLabel="country_name" optionValue="id" onChange={(e) => setForm({ ...form, to_country_id: e.value })} placeholder="Select Country" filter className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Product Type</label><InputText value={form.product_type} onChange={(e) => setForm({ ...form, product_type: e.target.value })} className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Slab Name</label><InputText value={form.slab_name} onChange={(e) => setForm({ ...form, slab_name: e.target.value })} className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Currency</label><InputText value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} placeholder="e.g. USD, EUR" className="w-full" /></div>
        </div>
      </Dialog>

      {/* Rate Dialog */}
      <Dialog header="Add Rate" visible={showRateDialog} onHide={() => setShowRateDialog(false)} style={{ width: '450px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowRateDialog(false)} /><Button label="Add Rate" icon="pi pi-check" onClick={handleAddRate} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2"><label className="font-medium">Rate *</label><InputNumber value={rateForm.rate} onValueChange={(e) => setRateForm({ ...rateForm, rate: e.value ?? null })} mode="decimal" minFractionDigits={2} className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Valid From *</label><Calendar value={rateForm.valid_from} onChange={(e) => setRateForm({ ...rateForm, valid_from: e.value as Date })} showIcon dateFormat="yy-mm-dd" className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Valid Till *</label><Calendar value={rateForm.valid_till} onChange={(e) => setRateForm({ ...rateForm, valid_till: e.value as Date })} showIcon dateFormat="yy-mm-dd" className="w-full" /></div>
        </div>
      </Dialog>

      {/* Import Dialog */}
      <Dialog header="Import Sea Master from Excel" visible={showImportDialog} onHide={() => { if (!importing) setShowImportDialog(false); }} style={{ width: '450px' }} modal closable={!importing}
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
