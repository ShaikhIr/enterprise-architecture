/**
 * Reusable Simple Master CRUD component.
 * React equivalent of O2C's Angular SimpleMasterComponent.
 * Handles table display, create/edit dialog, and soft-delete confirmation
 * for any single-field master entity.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { apiClient } from '@shared/services/apiClient';

interface SimpleMasterProps {
  /** Page title displayed at the top */
  title: string;
  /** Label for the form field */
  fieldLabel: string;
  /** The key used in API payloads (e.g. "brand_name", "dosage") */
  fieldKey: string;
  /** API path relative to /masters (e.g. "brands", "dosages") */
  apiPath: string;
}

interface MasterItem {
  id: string;
  is_active: boolean;
  [key: string]: unknown;
}

export const SimpleMaster = ({ title, fieldLabel, fieldKey, apiPath }: SimpleMasterProps) => {
  const toast = useRef<Toast>(null);
  const [items, setItems] = useState<MasterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [fieldValue, setFieldValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<MasterItem[]>(
        `/masters/${apiPath}`,
        { params: { include_inactive: true } }
      );
      setItems(data);
    } catch {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load data',
        life: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const openNew = () => {
    setEditingId(null);
    setFieldValue('');
    setError('');
    setShowDialog(true);
  };

  const openEdit = (item: MasterItem) => {
    setEditingId(item.id);
    setFieldValue(item[fieldKey] as string);
    setError('');
    setShowDialog(true);
  };

  const validate = (): boolean => {
    const trimmed = fieldValue.trim();
    if (!trimmed) {
      setError(`${fieldLabel} is required`);
      return false;
    }
    if (trimmed.length > 100) {
      setError(`${fieldLabel} must not exceed 100 characters`);
      return false;
    }
    setError('');
    return true;
  };

  const onSave = async () => {
    if (!validate()) return;

    setSaving(true);
    try {
      const payload = { [fieldKey]: fieldValue.trim() };
      if (editingId) {
        await apiClient.put(`/masters/${apiPath}/${editingId}`, payload);
      } else {
        await apiClient.post(`/masters/${apiPath}`, payload);
      }
      toast.current?.show({
        severity: 'success',
        summary: 'Saved',
        detail: `${title} saved successfully`,
        life: 3000,
      });
      setShowDialog(false);
      loadItems();
    } catch (e: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: e.response?.data?.detail || 'Save failed',
        life: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = (item: MasterItem) => {
    confirmDialog({
      message: `Deactivate "${item[fieldKey]}"?`,
      header: 'Confirm',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await apiClient.delete(`/masters/${apiPath}/${item.id}`);
          toast.current?.show({
            severity: 'success',
            summary: 'Deactivated',
            detail: `${title} deactivated successfully`,
            life: 3000,
          });
          loadItems();
        } catch {
          toast.current?.show({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to deactivate',
            life: 5000,
          });
        }
      },
    });
  };

  const statusTemplate = (rowData: MasterItem) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'secondary'}
    />
  );

  const actionsTemplate = (rowData: MasterItem) => (
    <div className="flex align-items-center gap-2">
      <Button
        icon="pi pi-pencil"
        rounded
        outlined
        severity="info"
        size="small"
        tooltip="Edit"
        tooltipOptions={{ position: 'top' }}
        onClick={() => openEdit(rowData)}
        aria-label={`Edit ${rowData[fieldKey]}`}
        style={{ width: '2rem', height: '2rem' }}
      />
      {rowData.is_active && (
        <Button
          icon="pi pi-trash"
          rounded
          outlined
          severity="danger"
          size="small"
          tooltip="Deactivate"
          tooltipOptions={{ position: 'top' }}
          onClick={() => confirmDelete(rowData)}
          aria-label={`Deactivate ${rowData[fieldKey]}`}
          style={{ width: '2rem', height: '2rem' }}
        />
      )}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <ConfirmDialog />

      <div className="flex justify-content-between align-items-center mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">{title} Master</h2>
        <Button label={`Add ${title}`} icon="pi pi-plus" onClick={openNew} />
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <DataTable
          value={items}
          loading={loading}
          stripedRows
          paginator
          rows={15}
          emptyMessage="No records found"
          size="small"
          filterDisplay="row"
        >
          <Column
            field={fieldKey}
            header={fieldLabel}
            sortable
            filter
            filterPlaceholder={`Search ${fieldLabel.toLowerCase()}`}
            body={(rowData: MasterItem) => (
              <span className="font-semibold">{rowData[fieldKey] as string}</span>
            )}
          />
          <Column header="Status" body={statusTemplate} style={{ width: '8rem' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '10rem', textAlign: 'center' }} />
        </DataTable>
      </div>

      {/* Create / Edit Dialog */}
      <Dialog
        header={editingId ? `Edit ${title}` : `Add New ${title}`}
        visible={showDialog}
        onHide={() => setShowDialog(false)}
        style={{ width: '400px' }}
        modal
        footer={
          <div className="flex justify-content-end gap-2">
            <Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} />
            <Button
              label="Save"
              icon="pi pi-check"
              onClick={onSave}
              disabled={!fieldValue.trim() || saving}
              loading={saving}
            />
          </div>
        }
      >
        <div className="mt-3">
          <div className="flex flex-column gap-2">
            <label htmlFor={fieldKey} className="font-medium">
              {fieldLabel} *
            </label>
            <InputText
              id={fieldKey}
              value={fieldValue}
              onChange={(e) => {
                setFieldValue(e.target.value);
                if (error) setError('');
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && fieldValue.trim()) {
                  onSave();
                }
              }}
              placeholder={`Enter ${fieldLabel}`}
              className={error ? 'p-invalid w-full' : 'w-full'}
              autoFocus
            />
            {error && <small className="p-error">{error}</small>}
          </div>
        </div>
      </Dialog>
    </div>
  );
};
