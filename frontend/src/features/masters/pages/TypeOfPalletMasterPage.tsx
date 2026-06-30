/**
 * Type of Pallet Master page — Multi-field CRUD with Excel import.
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
import { Pallet, palletService } from '../services/masterDataService';

interface PalletForm {
  name: string;
  length: number | null;
  width: number | null;
  height: number | null;
  gross_weight_per_pack_type: number | null;
  volumetric_weight: number | null;
}

const emptyForm: PalletForm = {
  name: '',
  length: null,
  width: null,
  height: null,
  gross_weight_per_pack_type: null,
  volumetric_weight: null,
};

export const TypeOfPalletMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<Pallet[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<Pallet | null>(null);
  const [form, setForm] = useState<PalletForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const { data } = await palletService.list(true);
      setRecords(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load pallet types', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const openNew = () => {
    setEditingRecord(null);
    setForm(emptyForm);
    setShowDialog(true);
  };

  const openEdit = (record: Pallet) => {
    setEditingRecord(record);
    setForm({
      name: record.name,
      length: record.length,
      width: record.width,
      height: record.height,
      gross_weight_per_pack_type: record.gross_weight_per_pack_type,
      volumetric_weight: record.volumetric_weight,
    });
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Pallet name is required', life: 3000 });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { ...form, name: form.name.trim() };
      if (editingRecord) {
        await palletService.update(editingRecord.id, payload);
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Pallet type updated successfully', life: 3000 });
      } else {
        await palletService.create(payload);
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Pallet type created successfully', life: 3000 });
      }
      setShowDialog(false);
      loadData();
    } catch (e: any) {
      const detail = e.response?.data?.detail || 'Operation failed';
      toast.current?.show({ severity: 'error', summary: 'Error', detail, life: 5000 });
    } finally {
      setSubmitting(false);
    }
  };

  const handleExcelImport = async () => {
    if (!importFile) return;
    setImporting(true);
    try {
      const { data } = await palletService.importExcel(importFile);
      toast.current?.show({
        severity: 'success',
        summary: 'Import Complete',
        detail: `Created: ${data.created}, Skipped: ${data.skipped}`,
        life: 5000,
      });
      setShowImportDialog(false);
      setImportFile(null);
      loadData();
    } catch (e: any) {
      const detail = e.response?.data?.detail || 'Import failed';
      toast.current?.show({ severity: 'error', summary: 'Error', detail, life: 5000 });
    } finally {
      setImporting(false);
    }
  };

  const downloadTemplate = async () => {
    try {
      const response = await palletService.downloadTemplate();
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'pallets_template.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template', life: 5000 });
    }
  };

  const confirmDelete = (record: Pallet) => {
    confirmDialog({
      message: `Are you sure you want to deactivate "${record.name}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: () => handleDelete(record.id),
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await palletService.delete(id);
      toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Pallet type deactivated', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Delete failed', life: 5000 });
    }
  };

  const statusTemplate = (row: Pallet) => (
    <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />
  );

  const actionsTemplate = (row: Pallet) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" rounded outlined size="small" tooltip="Edit" onClick={() => openEdit(row)} />
      {row.is_active && (
        <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" tooltip="Deactivate" onClick={() => confirmDelete(row)} />
      )}
    </div>
  );

  const dialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} />
      <Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} disabled={!form.name.trim()} />
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Type of Pallet Master</h2>
        <p className="text-600 mt-1 mb-0">Manage pallet type dimensions and weights</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar
          className="mb-3"
          start={() => (
            <div className="flex gap-2">
              <Button label="New Pallet Type" icon="pi pi-plus" onClick={openNew} />
              <Button label="Import Excel" icon="pi pi-file-excel" severity="success" outlined onClick={() => setShowImportDialog(true)} />
              <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
            </div>
          )}
        />

        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No pallet types found">
          <Column field="name" header="Pallet Name" sortable filter filterPlaceholder="Search..." />
          <Column field="length" header="Length" sortable />
          <Column field="width" header="Width" sortable />
          <Column field="height" header="Height" sortable />
          <Column field="gross_weight_per_pack_type" header="Gross Weight" sortable />
          <Column field="volumetric_weight" header="Volumetric Weight" sortable />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog
        header={editingRecord ? 'Edit Pallet Type' : 'New Pallet Type'}
        visible={showDialog}
        onHide={() => setShowDialog(false)}
        style={{ width: '550px' }}
        modal
        footer={dialogFooter}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label htmlFor="pallet_name" className="font-medium">Pallet Name *</label>
            <InputText
              id="pallet_name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Enter pallet name"
              autoFocus
              className="w-full"
            />
          </div>
          <div className="grid">
            <div className="col-6 flex flex-column gap-2">
              <label htmlFor="pallet_length" className="font-medium">Length</label>
              <InputNumber
                id="pallet_length"
                value={form.length}
                onValueChange={(e) => setForm({ ...form, length: e.value ?? null })}
                placeholder="mm"
                className="w-full"
              />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label htmlFor="pallet_width" className="font-medium">Width</label>
              <InputNumber
                id="pallet_width"
                value={form.width}
                onValueChange={(e) => setForm({ ...form, width: e.value ?? null })}
                placeholder="mm"
                className="w-full"
              />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label htmlFor="pallet_height" className="font-medium">Height</label>
              <InputNumber
                id="pallet_height"
                value={form.height}
                onValueChange={(e) => setForm({ ...form, height: e.value ?? null })}
                placeholder="mm"
                className="w-full"
              />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label htmlFor="pallet_gross_weight" className="font-medium">Gross Weight / Pack Type</label>
              <InputNumber
                id="pallet_gross_weight"
                value={form.gross_weight_per_pack_type}
                onValueChange={(e) => setForm({ ...form, gross_weight_per_pack_type: e.value ?? null })}
                placeholder="kg"
                className="w-full"
              />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label htmlFor="pallet_volumetric" className="font-medium">Volumetric Weight</label>
              <InputNumber
                id="pallet_volumetric"
                value={form.volumetric_weight}
                onValueChange={(e) => setForm({ ...form, volumetric_weight: e.value ?? null })}
                placeholder="kg"
                className="w-full"
              />
            </div>
          </div>
        </div>
      </Dialog>

      {/* Excel Import Dialog */}
      <Dialog
        header="Import Pallets from Excel"
        visible={showImportDialog}
        onHide={() => { if (!importing) setShowImportDialog(false); }}
        style={{ width: '450px' }}
        modal
        closable={!importing}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button label="Cancel" severity="secondary" text onClick={() => setShowImportDialog(false)} disabled={importing} />
            <Button label="Import" icon="pi pi-upload" onClick={handleExcelImport} disabled={!importFile || importing} loading={importing} />
          </div>
        }
      >
        {!importing ? (
          <div className="flex flex-column gap-3">
            <div>
              <a onClick={downloadTemplate} style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.85rem', cursor: 'pointer' }}>
                <i className="pi pi-download" style={{ marginRight: '0.3rem' }}></i>
                Download Template (Pallet Type, Length, Width, Height, Gross Weight, Volumetric Weight)
              </a>
            </div>
            <div className="flex flex-column gap-2">
              <label className="font-medium">Select Excel File (.xlsx / .xls)</label>
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
