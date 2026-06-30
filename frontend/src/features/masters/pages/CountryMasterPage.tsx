/**
 * Country Master page — CRUD with PrimeReact DataTable.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { Country, countryService } from '../services/freightMasterService';

interface CountryForm {
  country_name: string;
  country_code: string;
}
const emptyForm: CountryForm = { country_name: '', country_code: '' };

export const CountryMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<Country[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<Country | null>(null);
  const [form, setForm] = useState<CountryForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await countryService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load countries', life: 5000 }); }
    finally { setLoading(false); }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: Country) => { setEditingRecord(r); setForm({ country_name: r.country_name, country_code: r.country_code }); setShowDialog(true); };

  const handleSave = async () => {
    if (!form.country_name.trim() || !form.country_code.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Country name and code are required', life: 3000 });
      return;
    }
    setSubmitting(true);
    try {
      if (editingRecord) {
        await countryService.update(editingRecord.id, { country_name: form.country_name.trim(), country_code: form.country_code.trim().toUpperCase() });
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Country updated', life: 3000 });
      } else {
        await countryService.create({ country_name: form.country_name.trim(), country_code: form.country_code.trim().toUpperCase() });
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Country created', life: 3000 });
      }
      setShowDialog(false); loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 });
    } finally { setSubmitting(false); }
  };

  const confirmDelete = (r: Country) => {
    confirmDialog({ message: `Deactivate "${r.country_name}"?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) });
  };
  const handleDelete = async (id: string) => {
    try { await countryService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Country deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const statusTemplate = (row: Country) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const actionsTemplate = (row: Country) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Country Master</h2>
        <p className="text-600 mt-1 mb-0">Manage countries used by freight masters</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Country" icon="pi pi-plus" onClick={openNew} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No countries found">
          <Column field="country_name" header="Country Name" sortable filter filterPlaceholder="Search..." />
          <Column field="country_code" header="Code" sortable filter style={{ width: '10rem' }} />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      <Dialog header={editingRecord ? 'Edit Country' : 'New Country'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '400px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} disabled={!form.country_name.trim() || !form.country_code.trim()} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">Country Name *</label>
            <InputText value={form.country_name} onChange={(e) => setForm({ ...form, country_name: e.target.value })} placeholder="e.g. India" autoFocus className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Country Code *</label>
            <InputText value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })} placeholder="e.g. IN" maxLength={10} className="w-full" />
          </div>
        </div>
      </Dialog>
    </div>
  );
};
