/**
 * Local Master page — CRUD with rates, city/vehicle dropdowns, and Excel import.
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
  LocalMaster, City, VehicleType, Rate,
  localMasterService, cityService, vehicleTypeService,
} from '../services/freightMasterService';

interface LocalForm {
  from_city_id: string;
  to_city_id: string;
  product_type: string;
  vehicle_type_id: string;
  min_slab: string;
  max_slab: string;
}
const emptyForm: LocalForm = { from_city_id: '', to_city_id: '', product_type: '', vehicle_type_id: '', min_slab: '', max_slab: '' };

export const LocalMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<LocalMaster[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [vehicleTypes, setVehicleTypes] = useState<VehicleType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showRateDialog, setShowRateDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<LocalMaster | null>(null);
  const [selectedMaster, setSelectedMaster] = useState<LocalMaster | null>(null);
  const [form, setForm] = useState<LocalForm>(emptyForm);
  const [rateForm, setRateForm] = useState({ rate: null as number | null, valid_from: null as Date | null, valid_till: null as Date | null });
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [expandedRows, setExpandedRows] = useState<any>(null);

  useEffect(() => { loadData(); loadLookups(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await localMasterService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load Local Masters', life: 5000 }); }
    finally { setLoading(false); }
  };
  const loadLookups = async () => {
    try { const [c, v] = await Promise.all([cityService.list(), vehicleTypeService.list()]); setCities(c.data); setVehicleTypes(v.data); } catch { /* silent */ }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: LocalMaster) => { setEditingRecord(r); setForm({ from_city_id: r.from_city_id, to_city_id: r.to_city_id, product_type: r.product_type || '', vehicle_type_id: r.vehicle_type_id || '', min_slab: r.min_slab || '', max_slab: r.max_slab || '' }); setShowDialog(true); };

  const handleSave = async () => {
    if (!form.from_city_id || !form.to_city_id) { toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'From City and To City are required', life: 3000 }); return; }
    setSubmitting(true);
    try {
      const payload = { from_city_id: form.from_city_id, to_city_id: form.to_city_id, product_type: form.product_type || undefined, vehicle_type_id: form.vehicle_type_id || undefined, min_slab: form.min_slab || undefined, max_slab: form.max_slab || undefined };
      if (editingRecord) { await localMasterService.update(editingRecord.id, payload); toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Local Master updated', life: 3000 }); }
      else { await localMasterService.create(payload); toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Local Master created', life: 3000 }); }
      setShowDialog(false); loadData();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 }); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = (r: LocalMaster) => { confirmDialog({ message: `Deactivate Local Master (${r.from_city_name} → ${r.to_city_name})?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) }); };
  const handleDelete = async (id: string) => {
    try { await localMasterService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Local Master deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const openRateDialog = (r: LocalMaster) => { setSelectedMaster(r); setRateForm({ rate: null, valid_from: null, valid_till: null }); setShowRateDialog(true); };
  const handleAddRate = async () => {
    if (!selectedMaster || !rateForm.rate || !rateForm.valid_from || !rateForm.valid_till) { toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'All rate fields required', life: 3000 }); return; }
    try { await localMasterService.addRate(selectedMaster.id, { rate: rateForm.rate, valid_from: rateForm.valid_from.toISOString(), valid_till: rateForm.valid_till.toISOString() }); toast.current?.show({ severity: 'success', summary: 'Added', detail: 'Rate added', life: 3000 }); setShowRateDialog(false); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };
  const handleDeleteRate = async (rateId: string) => {
    try { await localMasterService.deleteRate(rateId); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Rate deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const handleExcelImport = async () => {
    if (!importFile) return; setImporting(true);
    try { const { data } = await localMasterService.importExcel(importFile); toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message || 'Done', life: 5000 }); setShowImportDialog(false); setImportFile(null); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Import failed', life: 5000 }); }
    finally { setImporting(false); }
  };
  const downloadTemplate = async () => {
    try { const response = await localMasterService.downloadTemplate(); const url = window.URL.createObjectURL(new Blob([response.data])); const a = document.createElement('a'); a.href = url; a.download = 'local_master_template.xlsx'; a.click(); window.URL.revokeObjectURL(url); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Template download failed', life: 5000 }); }
  };

  const statusTemplate = (row: LocalMaster) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const ratesTemplate = (row: LocalMaster) => { const ar = (row.rates || []).filter(r => r.is_active); return <span>{ar.length > 0 ? `${ar[0].rate}` : '—'}</span>; };
  const actionsTemplate = (row: LocalMaster) => (
    <div className="flex gap-1">
      <Button icon="pi pi-plus-circle" rounded outlined size="small" tooltip="Add Rate" onClick={() => openRateDialog(row)} />
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );
  const rowExpansionTemplate = (row: LocalMaster) => {
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
        <h2 className="text-xl font-semibold text-900 m-0">Local Master</h2>
        <p className="text-600 mt-1 mb-0">Manage local freight rates between cities</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Local Master" icon="pi pi-plus" onClick={openNew} />
            <Button label="Import Excel" icon="pi pi-file-excel" severity="success" outlined onClick={() => setShowImportDialog(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} dataKey="id" expandedRows={expandedRows} onRowToggle={(e) => setExpandedRows(e.data)} rowExpansionTemplate={rowExpansionTemplate} emptyMessage="No local masters found">
          <Column expander style={{ width: '3rem' }} />
          <Column field="from_city_name" header="From City" sortable filter filterPlaceholder="Search..." />
          <Column field="to_city_name" header="To City" sortable filter filterPlaceholder="Search..." />
          <Column field="product_type" header="Product Type" sortable filter />
          <Column field="vehicle_type_name" header="Vehicle Type" sortable />
          <Column field="min_slab" header="Min Slab" sortable />
          <Column field="max_slab" header="Max Slab" sortable />
          <Column header="Rates" body={ratesTemplate} />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '10rem' }} />
        </DataTable>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog header={editingRecord ? 'Edit Local Master' : 'New Local Master'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '550px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="grid">
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">From City *</label><Dropdown value={form.from_city_id} options={cities} optionLabel="city_name" optionValue="id" onChange={(e) => setForm({ ...form, from_city_id: e.value })} placeholder="Select" filter className="w-full" /></div>
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">To City *</label><Dropdown value={form.to_city_id} options={cities} optionLabel="city_name" optionValue="id" onChange={(e) => setForm({ ...form, to_city_id: e.value })} placeholder="Select" filter className="w-full" /></div>
          </div>
          <div className="flex flex-column gap-2"><label className="font-medium">Product Type</label><InputText value={form.product_type} onChange={(e) => setForm({ ...form, product_type: e.target.value })} className="w-full" /></div>
          <div className="flex flex-column gap-2"><label className="font-medium">Vehicle Type</label><Dropdown value={form.vehicle_type_id} options={vehicleTypes} optionLabel="vehicle_type" optionValue="id" onChange={(e) => setForm({ ...form, vehicle_type_id: e.value })} placeholder="Select" filter showClear className="w-full" /></div>
          <div className="grid">
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">Min Slab</label><InputText value={form.min_slab} onChange={(e) => setForm({ ...form, min_slab: e.target.value })} className="w-full" /></div>
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">Max Slab</label><InputText value={form.max_slab} onChange={(e) => setForm({ ...form, max_slab: e.target.value })} className="w-full" /></div>
          </div>
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
      <Dialog header="Import Local Master from Excel" visible={showImportDialog} onHide={() => { if (!importing) setShowImportDialog(false); }} style={{ width: '450px' }} modal closable={!importing}
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
