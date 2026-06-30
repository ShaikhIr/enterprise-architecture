/**
 * City Master page — CRUD with country dropdown.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { City, Country, cityService, countryService } from '../services/freightMasterService';

interface CityForm {
  city_name: string;
  country_id: string;
}
const emptyForm: CityForm = { city_name: '', country_id: '' };

export const CityMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<City[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<City | null>(null);
  const [form, setForm] = useState<CityForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { loadData(); loadCountries(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await cityService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load cities', life: 5000 }); }
    finally { setLoading(false); }
  };
  const loadCountries = async () => {
    try { const { data } = await countryService.list(); setCountries(data); } catch { /* silent */ }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: City) => { setEditingRecord(r); setForm({ city_name: r.city_name, country_id: r.country_id || '' }); setShowDialog(true); };

  const handleSave = async () => {
    if (!form.city_name.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'City name is required', life: 3000 });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { city_name: form.city_name.trim(), country_id: form.country_id || undefined };
      if (editingRecord) {
        await cityService.update(editingRecord.id, payload);
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'City updated', life: 3000 });
      } else {
        await cityService.create(payload);
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'City created', life: 3000 });
      }
      setShowDialog(false); loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 });
    } finally { setSubmitting(false); }
  };

  const confirmDelete = (r: City) => {
    confirmDialog({ message: `Deactivate "${r.city_name}"?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) });
  };
  const handleDelete = async (id: string) => {
    try { await cityService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'City deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const statusTemplate = (row: City) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const actionsTemplate = (row: City) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">City Master</h2>
        <p className="text-600 mt-1 mb-0">Manage cities used by local freight masters</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New City" icon="pi pi-plus" onClick={openNew} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No cities found">
          <Column field="city_name" header="City Name" sortable filter filterPlaceholder="Search..." />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      <Dialog header={editingRecord ? 'Edit City' : 'New City'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '400px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} disabled={!form.city_name.trim()} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">City Name *</label>
            <InputText value={form.city_name} onChange={(e) => setForm({ ...form, city_name: e.target.value })} placeholder="e.g. Mumbai" autoFocus className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Country</label>
            <Dropdown value={form.country_id} options={countries} optionLabel="country_name" optionValue="id" onChange={(e) => setForm({ ...form, country_id: e.value })} placeholder="Select Country (optional)" filter showClear className="w-full" />
          </div>
        </div>
      </Dialog>
    </div>
  );
};
