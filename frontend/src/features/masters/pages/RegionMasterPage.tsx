/**
 * Region Master Page.
 * Full CRUD with PrimeReact DataTable, add/edit dialog, import dialog, and soft-delete.
 */

import { useState, useEffect, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { regionApi, Region } from '../api/regionApi';

export const RegionMasterPage = () => {
  const [regions, setRegions] = useState<Region[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [regionName, setRegionName] = useState('');
  const [regionId, setRegionId] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [nameError, setNameError] = useState('');
  const toast = useRef<Toast>(null);

  const loadRegions = async () => {
    setLoading(true);
    try {
      const data = await regionApi.getRegions(true);
      setRegions(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load regions' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRegions();
  }, []);

  const openNew = () => {
    setEditingId(null);
    setRegionName('');
    setRegionId('');
    setNameError('');
    setShowDialog(true);
  };

  const editRegion = (region: Region) => {
    setEditingId(region.id);
    setRegionName(region.region_name);
    setRegionId(region.region_id || '');
    setNameError('');
    setShowDialog(true);
  };

  const saveRegion = async () => {
    if (!regionName.trim()) {
      setNameError('Region name is required');
      return;
    }

    try {
      if (editingId) {
        await regionApi.updateRegion(editingId, {
          region_name: regionName.trim(),
          region_id: regionId.trim() || undefined,
        });
      } else {
        await regionApi.createRegion({
          region_name: regionName.trim(),
          region_id: regionId.trim() || undefined,
        });
      }
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Region saved successfully' });
      setShowDialog(false);
      loadRegions();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to save region';
      toast.current?.show({ severity: 'error', summary: 'Error', detail });
    }
  };

  const confirmDelete = (region: Region) => {
    confirmDialog({
      message: `Are you sure you want to deactivate region "${region.region_name}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await regionApi.deleteRegion(region.id);
          toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Region deactivated' });
          loadRegions();
        } catch (err: any) {
          const detail = err.response?.data?.detail || 'Failed to deactivate region';
          toast.current?.show({ severity: 'error', summary: 'Error', detail });
        }
      },
    });
  };

  const downloadTemplate = async () => {
    try {
      await regionApi.downloadTemplate();
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template' });
    }
  };

  const importExcel = async () => {
    if (!importFile) return;
    try {
      const result = await regionApi.importExcel(importFile);
      toast.current?.show({
        severity: 'success',
        summary: 'Import Complete',
        detail: `Created: ${result.created}, Skipped: ${result.skipped}`,
      });
      setShowImportDialog(false);
      setImportFile(null);
      loadRegions();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to import';
      toast.current?.show({ severity: 'error', summary: 'Import Failed', detail });
    }
  };

  // Column templates
  const statusTemplate = (rowData: Region) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'secondary' as any}
    />
  );

  const actionsTemplate = (rowData: Region) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" text size="small" onClick={() => editRegion(rowData)} aria-label="Edit" />
      {rowData.is_active && (
        <Button icon="pi pi-trash" text severity="danger" size="small" onClick={() => confirmDelete(rowData)} aria-label="Deactivate" />
      )}
    </div>
  );

  const dialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" text onClick={() => setShowDialog(false)} />
      <Button label="Save" onClick={saveRegion} disabled={!regionName.trim()} />
    </div>
  );

  const importDialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" text onClick={() => setShowImportDialog(false)} />
      <Button label="Import" icon="pi pi-upload" onClick={importExcel} disabled={!importFile} />
    </div>
  );

  return (
    <div className="p-4">
      <Toast ref={toast} />
      <ConfirmDialog />

      {/* Header */}
      <div className="flex justify-content-between align-items-center mb-4">
        <h2 className="m-0" style={{ color: 'var(--color-text-primary)' }}>Region Master</h2>
        <div className="flex gap-2">
          <Button
            label="Import Excel"
            icon="pi pi-file-excel"
            severity="success"
            size="small"
            onClick={() => setShowImportDialog(true)}
          />
          <Button
            label="Add Region"
            icon="pi pi-plus"
            size="small"
            onClick={openNew}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="card">
        <DataTable
          value={regions}
          loading={loading}
          paginator
          rows={15}
          size="small"
          stripedRows
          emptyMessage="No regions found"
          sortField="region_name"
          sortOrder={1}
        >
          <Column field="region_id" header="Region ID" sortable style={{ width: '150px' }} body={(row) => row.region_id || '—'} />
          <Column field="region_name" header="Region Name" sortable />
          <Column header="Status" body={statusTemplate} style={{ width: '120px' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '120px' }} />
        </DataTable>
      </div>

      {/* Add/Edit Dialog */}
      <Dialog
        visible={showDialog}
        header={editingId ? 'Edit Region' : 'Add New Region'}
        modal
        style={{ width: '400px' }}
        footer={dialogFooter}
        onHide={() => setShowDialog(false)}
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-1">
            <label htmlFor="region_id" className="font-medium text-sm">Region ID</label>
            <InputText
              id="region_id"
              value={regionId}
              onChange={(e) => setRegionId(e.target.value)}
              placeholder="Enter region ID"
              className="w-full"
            />
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="region_name" className="font-medium text-sm">Region Name *</label>
            <InputText
              id="region_name"
              value={regionName}
              onChange={(e) => { setRegionName(e.target.value); setNameError(''); }}
              placeholder="Enter region name"
              className={`w-full ${nameError ? 'p-invalid' : ''}`}
            />
            {nameError && <small className="p-error">{nameError}</small>}
          </div>
        </div>
      </Dialog>

      {/* Import Excel Dialog */}
      <Dialog
        visible={showImportDialog}
        header="Import Regions from Excel"
        modal
        style={{ width: '450px' }}
        footer={importDialogFooter}
        onHide={() => setShowImportDialog(false)}
      >
        <div className="flex flex-column gap-3 pt-2">
          <div>
            <a
              onClick={downloadTemplate}
              style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.85rem', cursor: 'pointer' }}
            >
              <i className="pi pi-download mr-1" />
              Download Template (Region ID, Region Name)
            </a>
          </div>
          <div className="flex flex-column gap-1">
            <label className="font-medium text-sm">Select Excel File (.xlsx / .xls)</label>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setImportFile(e.target.files?.[0] || null)}
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
};
