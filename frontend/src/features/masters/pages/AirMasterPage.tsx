/**
 * Air Master page — CRUD with rates management and Excel import.
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
  AirMaster,
  Country,
  Rate,
  airMasterService,
  countryService,
} from '../services/freightMasterService';

interface AirForm {
  to_country_id: string;
  product_type: string;
  min_slab: number | null;
  max_slab: number | null;
}

const emptyForm: AirForm = {
  to_country_id: '',
  product_type: '',
  min_slab: null,
  max_slab: null,
};

export const AirMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<AirMaster[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showRateDialog, setShowRateDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<AirMaster | null>(null);
  const [selectedMaster, setSelectedMaster] = useState<AirMaster | null>(null);
  const [form, setForm] = useState<AirForm>(emptyForm);
  const [rateForm, setRateForm] = useState({ rate: null as number | null, valid_from: null as Date | null, valid_till: null as Date | null });
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  useEffect(() => { loadData(); loadCountries(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const { data } = await airMasterService.list(true);
      setRecords(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load Air Masters', life: 5000 });
    } finally { setLoading(false); }
  };

  const loadCountries = async () => {
    try {
      const { data } = await countryService.list();
      setCountries(data);
    } catch { /* silent */ }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (record: AirMaster) => {
    setEditingRecord(record);
    setForm({ to_country_id: record.to_country_id, product_type: record.product_type || '', min_slab: record.min_slab, max_slab: record.max_slab });
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.to_country_id || form.min_slab === null || form.max_slab === null) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Country, Min Slab, and Max Slab are required', life: 3000 });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { to_country_id: form.to_country_id, product_type: form.product_type || undefined, min_slab: form.min_slab, max_slab: form.max_slab };
      if (editingRecord) {
        await airMasterService.update(editingRecord.id, payload);
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Air Master updated', life: 3000 });
      } else {
        await airMasterService.create(payload);
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Air Master created', life: 3000 });
      }
      setShowDialog(false); loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 });
    } finally { setSubmitting(false); }
  };

  const confirmDelete = (record: AirMaster) => {
    confirmDialog({
      message: `Deactivate Air Master "${record.slab_name}" for ${record.country_name}?`,
      header: 'Confirm Deactivation', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger',
      accept: () => handleDelete(record.id),
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await airMasterService.delete(id);
      toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Air Master deactivated', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  // --- Rate management ---
  const openRateDialog = (record: AirMaster) => { setSelectedMaster(record); setRateForm({ rate: null, valid_from: null, valid_till: null }); setShowRateDialog(true); };

  const handleAddRate = async () => {
    if (!selectedMaster || !rateForm.rate || !rateForm.valid_from || !rateForm.valid_till) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'All rate fields are required', life: 3000 });
      return;
    }
    try {
      await airMasterService.addRate(selectedMaster.id, {
        rate: rateForm.rate,
        valid_from: rateForm.valid_from.toISOString(),
        valid_till: rateForm.valid_till.toISOString(),
      });
      toast.current?.show({ severity: 'success', summary: 'Added', detail: 'Rate added', life: 3000 });
      setShowRateDialog(false); loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const handleDeleteRate = async (rateId: string) => {
    try {
      await airMasterService.deleteRate(rateId);
      toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Rate deactivated', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  // --- Excel import ---
  const handleExcelImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try {
      const { data } = await airMasterService.importExcel(importFile);
      toast.current?.show({ severity: 'success', summary: 'Import Complete', detail: data.message || 'Import done', life: 5000 });
      setShowImportDialog(false); setImportFile(null); loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Import failed', life: 5000 });
    } finally { setImporting(false); }
  };

  const downloadTemplate = async () => {
    try {
      const response = await airMasterService.downloadTemplate();
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a'); a.href = url; a.download = 'air_master_template.xlsx'; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template', life: 5000 }); }
  };

  // --- Templates ---
  const statusTemplate = (row: AirMaster) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const ratesTemplate = (row: AirMaster) => {
    const activeRates = (row.rates || []).filter(r => r.is_active);
    const firstRate = activeRates[0];
    return <span>{firstRate ? `${firstRate.rate}` : '—'}</span>;
  };
  const actionsTemplate = (row: AirMaster) => (
    <div className="flex gap-1">
      <Button icon="pi pi-plus-circle" rounded outlined size="small" tooltip="Add Rate" onClick={() => openRateDialog(row)} />
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );

  const rowExpansionTemplate = (row: AirMaster) => {
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

  const [expandedRows, setExpandedRows] = useState<any>(null);

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Air Master</h2>
        <p className="text-600 mt-1 mb-0">Manage air freight slab rates by country and product type</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Air Master" icon="pi pi-plus" onClick={openNew} />
            <Button label="Import Excel" icon="pi pi-file-excel" severity="success" outlined onClick={() => setShowImportDialog(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />

        <DataTable value={records} loading={loading} stripedRows paginator rows={10} dataKey="id" expandedRows={expandedRows} onRowToggle={(e) => setExpandedRows(e.data)} rowExpansionTemplate={rowExpansionTemplate} emptyMessage="No air masters found">
          <Column expander style={{ width: '3rem' }} />
          <Column field="country_name" header="Country Name" sortable filter filterPlaceholder="Search..." />
          <Column field="country_code" header="Country Code" sortable filter />
          <Column field="product_type" header="Product Type" sortable filter filterPlaceholder="Search..." />
          <Column field="min_slab" header="Min Slab" sortable />
          <Column field="max_slab" header="Max Slab" sortable />
          <Column field="slab_name" header="Slab Name" sortable />
          <Column header="Rates" body={ratesTemplate} />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '10rem' }} />
        </DataTable>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog header={editingRecord ? 'Edit Air Master' : 'New Air Master'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '500px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">Country *</label>
            <Dropdown value={form.to_country_id} options={countries} optionLabel="country_name" optionValue="id" onChange={(e) => setForm({ ...form, to_country_id: e.value })} placeholder="Select Country" filter className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Product Type</label>
            <InputText value={form.product_type} onChange={(e) => setForm({ ...form, product_type: e.target.value })} placeholder="e.g. Pharma, Chemical" className="w-full" />
          </div>
          <div className="grid">
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Min Slab (KG) *</label>
              <InputNumber value={form.min_slab} onValueChange={(e) => setForm({ ...form, min_slab: e.value ?? null })} placeholder="0" className="w-full" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Max Slab (KG) *</label>
              <InputNumber value={form.max_slab} onValueChange={(e) => setForm({ ...form, max_slab: e.value ?? null })} placeholder="999" className="w-full" />
            </div>
          </div>
        </div>
      </Dialog>

      {/* Add Rate Dialog */}
      <Dialog header="Add Rate" visible={showRateDialog} onHide={() => setShowRateDialog(false)} style={{ width: '450px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowRateDialog(false)} /><Button label="Add Rate" icon="pi pi-check" onClick={handleAddRate} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">Rate *</label>
            <InputNumber value={rateForm.rate} onValueChange={(e) => setRateForm({ ...rateForm, rate: e.value ?? null })} mode="decimal" minFractionDigits={2} className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Valid From *</label>
            <Calendar value={rateForm.valid_from} onChange={(e) => setRateForm({ ...rateForm, valid_from: e.value as Date })} showIcon dateFormat="yy-mm-dd" className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Valid Till *</label>
            <Calendar value={rateForm.valid_till} onChange={(e) => setRateForm({ ...rateForm, valid_till: e.value as Date })} showIcon dateFormat="yy-mm-dd" className="w-full" />
          </div>
        </div>
      </Dialog>

      {/* Excel Import Dialog */}
      <Dialog header="Import Air Master from Excel" visible={showImportDialog} onHide={() => { if (!importing) setShowImportDialog(false); }} style={{ width: '450px' }} modal closable={!importing}
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowImportDialog(false)} disabled={importing} /><Button label="Import" icon="pi pi-upload" onClick={handleExcelImport} disabled={!importFile || importing} loading={importing} /></div>}>
        {!importing ? (
          <div className="flex flex-column gap-3">
            <div>
              <a onClick={downloadTemplate} style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.85rem', cursor: 'pointer' }}>
                <i className="pi pi-download" style={{ marginRight: '0.3rem' }}></i>
                Download Template
              </a>
            </div>
            <div className="flex flex-column gap-2">
              <label className="font-medium">Select Excel File (.xlsx)</label>
              <input type="file" accept=".xlsx,.xls" onChange={(e) => setImportFile(e.target.files?.[0] || null)} />
            </div>
          </div>
        ) : (
          <div className="flex flex-column align-items-center gap-3 py-4">
            <i className="pi pi-spin pi-spinner" style={{ fontSize: '2rem', color: '#2563eb' }}></i>
            <p className="font-medium m-0">Importing... Please wait</p>
          </div>
        )}
      </Dialog>
    </div>
  );
};
