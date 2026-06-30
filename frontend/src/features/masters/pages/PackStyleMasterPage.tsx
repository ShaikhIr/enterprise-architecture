/**
 * Pack Style Master page — CRUD with PrimeReact DataTable and Dialog.
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
import { PackStyle, packStyleService } from '../services/masterDataService';

export const PackStyleMasterPage = () => {
  const toast = useRef<Toast>(null);
  const [records, setRecords] = useState<PackStyle[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState<PackStyle | null>(null);
  const [formValue, setFormValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const { data } = await packStyleService.list(true);
      setRecords(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load pack styles', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const openNew = () => {
    setEditingRecord(null);
    setFormValue('');
    setShowDialog(true);
  };

  const openEdit = (record: PackStyle) => {
    setEditingRecord(record);
    setFormValue(record.pack_style);
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!formValue.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Pack Style is required', life: 3000 });
      return;
    }
    setSubmitting(true);
    try {
      if (editingRecord) {
        await packStyleService.update(editingRecord.id, { pack_style: formValue.trim() });
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Pack Style updated successfully', life: 3000 });
      } else {
        await packStyleService.create({ pack_style: formValue.trim() });
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Pack Style created successfully', life: 3000 });
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

  const confirmDelete = (record: PackStyle) => {
    confirmDialog({
      message: `Are you sure you want to deactivate "${record.pack_style}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: () => handleDelete(record.id),
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await packStyleService.delete(id);
      toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Pack Style deactivated', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Delete failed', life: 5000 });
    }
  };

  const statusTemplate = (row: PackStyle) => (
    <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />
  );

  const actionsTemplate = (row: PackStyle) => (
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
      <Button label="Save" icon="pi pi-check" onClick={handleSave} loading={submitting} disabled={!formValue.trim()} />
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <ConfirmDialog />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Pack Style Master</h2>
        <p className="text-600 mt-1 mb-0">Manage pack style configurations</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar
          className="mb-3"
          start={() => (
            <div className="flex gap-2">
              <Button label="New Pack Style" icon="pi pi-plus" onClick={openNew} />
              <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
            </div>
          )}
        />

        <DataTable value={records} loading={loading} stripedRows paginator rows={10} emptyMessage="No pack styles found">
          <Column field="pack_style" header="Pack Style" sortable filter filterPlaceholder="Search..." />
          <Column header="Status" body={statusTemplate} sortable field="is_active" style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      <Dialog
        header={editingRecord ? 'Edit Pack Style' : 'New Pack Style'}
        visible={showDialog}
        onHide={() => setShowDialog(false)}
        style={{ width: '400px' }}
        modal
        footer={dialogFooter}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label htmlFor="pack_style" className="font-medium">Pack Style</label>
            <InputText
              id="pack_style"
              value={formValue}
              onChange={(e) => setFormValue(e.target.value)}
              placeholder="Enter pack style"
              autoFocus
              className="w-full"
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
};
