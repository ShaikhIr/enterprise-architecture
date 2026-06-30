/**
 * Vehicle Type Master page — CRUD with PrimeReact DataTable.
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
import { VehicleType, vehicleTypeService } from '../services/freightMasterService';

interface VtForm {
  from_no_of_pallet_or_box: number | null;
  to_no_of_pallet_or_box: number | null;
  vehicle_type: string;
}
const emptyForm: VtForm = { from_no_of_pallet_or_box: null, to_no_of_pallet_or_box: null, vehicle_type: '' };

export const VehicleTypeMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<VehicleType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<VehicleType | null>(null);
  const [form, setForm] = useState<VtForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try { const { data } = await vehicleTypeService.list(true); setRecords(data); }
    catch { toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load Vehicle Types', life: 5000 }); }
    finally { setLoading(false); }
  };

  const openNew = () => { setEditingRecord(null); setForm(emptyForm); setShowDialog(true); };
  const openEdit = (r: VehicleType) => { setEditingRecord(r); setForm({ from_no_of_pallet_or_box: r.from_no_of_pallet_or_box, to_no_of_pallet_or_box: r.to_no_of_pallet_or_box, vehicle_type: r.vehicle_type }); setShowDialog(true); };

  const handleSave = async () => {
    if (!form.vehicle_type.trim() || form.from_no_of_pallet_or_box === null || form.to_no_of_pallet_or_box === null) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'All fields are required', life: 3000 }); return;
    }
    setSubmitting(true);
    try {
      const payload = { from_no_of_pallet_or_box: form.from_no_of_pallet_or_box, to_no_of_pallet_or_box: form.to_no_of_pallet_or_box, vehicle_type: form.vehicle_type.trim() };
      if (editingRecord) { await vehicleTypeService.update(editingRecord.id, payload); toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Vehicle Type updated', life: 3000 }); }
      else { await vehicleTypeService.create(payload); toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Vehicle Type created', life: 3000 }); }
      setShowDialog(false); loadData();
    } catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Operation failed', life: 5000 }); }
    finally { setSubmitting(false); }
  };

  const confirmDelete = (r: VehicleType) => { confirmDialog({ message: `Deactivate "${r.vehicle_type}"?`, header: 'Confirm', icon: 'pi pi-exclamation-triangle', acceptClassName: 'p-button-danger', accept: () => handleDelete(r.id) }); };
  const handleDelete = async (id: string) => {
    try { await vehicleTypeService.delete(id); toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Vehicle Type deactivated', life: 3000 }); loadData(); }
    catch (e: any) { toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 }); }
  };

  const statusTemplate = (row: VehicleType) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />;
  const actionsTemplate = (row: VehicleType) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} /><ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Vehicle Type Master</h2>
        <p className="text-600 mt-1 mb-0">Manage vehicle type definitions by pallet/box count</p>
      </div>
      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Vehicle Type" icon="pi pi-plus" onClick={openNew} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />
        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No vehicle types found">
          <Column field="from_no_of_pallet_or_box" header="From # Pallet/Box" sortable />
          <Column field="to_no_of_pallet_or_box" header="To # Pallet/Box" sortable />
          <Column field="vehicle_type" header="Vehicle Type" sortable filter filterPlaceholder="Search..." />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      <Dialog header={editingRecord ? 'Edit Vehicle Type' : 'New Vehicle Type'} visible={showDialog} onHide={() => setShowDialog(false)} style={{ width: '450px' }} modal
        footer={<div className="flex justify-content-end gap-2"><Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} /><Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} /></div>}>
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2"><label className="font-medium">Vehicle Type *</label><InputText value={form.vehicle_type} onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })} placeholder="e.g. 14ft, 20ft Container" className="w-full" /></div>
          <div className="grid">
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">From Pallets/Boxes *</label><InputNumber value={form.from_no_of_pallet_or_box} onValueChange={(e) => setForm({ ...form, from_no_of_pallet_or_box: e.value ?? null })} className="w-full" /></div>
            <div className="col-6 flex flex-column gap-2"><label className="font-medium">To Pallets/Boxes *</label><InputNumber value={form.to_no_of_pallet_or_box} onValueChange={(e) => setForm({ ...form, to_no_of_pallet_or_box: e.value ?? null })} className="w-full" /></div>
          </div>
        </div>
      </Dialog>
    </div>
  );
};
