/**
 * City Master Page.
 * Full CRUD with PrimeReact DataTable, add/edit dialog with state dropdown,
 * import dialog, and soft-delete.
 */

import { useState, useEffect, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { cityApi, City } from '../api/cityApi';
import { stateApi, State } from '../api/stateApi';

export const CityMasterPage = () => {
  const [cities, setCities] = useState<City[]>([]);
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedStateId, setSelectedStateId] = useState<string | null>(null);
  const [cityName, setCityName] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useRef<Toast>(null);

  const loadCities = async () => {
    setLoading(true);
    try {
      const data = await cityApi.getCities(true);
      setCities(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load cities' });
    } finally {
      setLoading(false);
    }
  };

  const loadStates = async () => {
    try {
      const data = await stateApi.getStates(false);
      setStates(data);
    } catch {
      // Silent fail
    }
  };

  useEffect(() => {
    loadCities();
    loadStates();
  }, []);

  const openNew = () => {
    setEditingId(null);
    setSelectedStateId(null);
    setCityName('');
    setErrors({});
    setShowDialog(true);
  };

  const editCity = (city: City) => {
    setEditingId(city.id);
    setSelectedStateId(city.state_id);
    setCityName(city.city_name);
    setErrors({});
    setShowDialog(true);
  };

  const saveCity = async () => {
    const newErrors: Record<string, string> = {};
    if (!selectedStateId) newErrors.state_id = 'State is required';
    if (!cityName.trim()) newErrors.city_name = 'City name is required';
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    try {
      if (editingId) {
        await cityApi.updateCity(editingId, {
          state_id: selectedStateId!,
          city_name: cityName.trim(),
        });
      } else {
        await cityApi.createCity({
          state_id: selectedStateId!,
          city_name: cityName.trim(),
        });
      }
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'City saved successfully' });
      setShowDialog(false);
      loadCities();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to save city';
      toast.current?.show({ severity: 'error', summary: 'Error', detail });
    }
  };

  const confirmDelete = (city: City) => {
    confirmDialog({
      message: `Are you sure you want to deactivate "${city.city_name}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await cityApi.deleteCity(city.id);
          toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'City deactivated' });
          loadCities();
        } catch (err: any) {
          const detail = err.response?.data?.detail || 'Failed to deactivate city';
          toast.current?.show({ severity: 'error', summary: 'Error', detail });
        }
      },
    });
  };

  const downloadTemplate = async () => {
    try {
      await cityApi.downloadTemplate();
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template' });
    }
  };

  const importExcel = async () => {
    if (!importFile) return;
    try {
      const result = await cityApi.importExcel(importFile);
      toast.current?.show({
        severity: 'success',
        summary: 'Import Complete',
        detail: `Created: ${result.created}, Skipped: ${result.skipped}`,
      });
      setShowImportDialog(false);
      setImportFile(null);
      loadCities();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to import';
      toast.current?.show({ severity: 'error', summary: 'Import Failed', detail });
    }
  };

  const statusTemplate = (rowData: City) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'secondary' as any}
    />
  );

  const actionsTemplate = (rowData: City) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" text size="small" onClick={() => editCity(rowData)} aria-label="Edit" />
      {rowData.is_active && (
        <Button icon="pi pi-trash" text severity="danger" size="small" onClick={() => confirmDelete(rowData)} aria-label="Deactivate" />
      )}
    </div>
  );

  const isFormValid = !!selectedStateId && !!cityName.trim();

  const dialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" text onClick={() => setShowDialog(false)} />
      <Button label="Save" onClick={saveCity} disabled={!isFormValid} />
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
        <h2 className="m-0" style={{ color: 'var(--color-text-primary)' }}>City Master</h2>
        <div className="flex gap-2">
          <Button
            label="Import Excel"
            icon="pi pi-file-excel"
            severity="success"
            size="small"
            onClick={() => setShowImportDialog(true)}
          />
          <Button
            label="Add City"
            icon="pi pi-plus"
            size="small"
            onClick={openNew}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="card">
        <DataTable
          value={cities}
          loading={loading}
          paginator
          rows={15}
          size="small"
          stripedRows
          emptyMessage="No cities found"
          sortField="city_name"
          sortOrder={1}
        >
          <Column field="city_name" header="City Name" sortable />
          <Column field="state_name" header="State" sortable body={(row) => row.state_name || '—'} />
          <Column header="Status" body={statusTemplate} style={{ width: '120px' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '120px' }} />
        </DataTable>
      </div>

      {/* Add/Edit Dialog */}
      <Dialog
        visible={showDialog}
        header={editingId ? 'Edit City' : 'Add New City'}
        modal
        style={{ width: '420px' }}
        footer={dialogFooter}
        onHide={() => setShowDialog(false)}
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-1">
            <label htmlFor="state_id" className="font-medium text-sm">State *</label>
            <Dropdown
              id="state_id"
              value={selectedStateId}
              onChange={(e) => { setSelectedStateId(e.value); setErrors({ ...errors, state_id: '' }); }}
              options={states}
              optionLabel="state_name"
              optionValue="id"
              filter
              placeholder="Select state"
              className={`w-full ${errors.state_id ? 'p-invalid' : ''}`}
            />
            {errors.state_id && <small className="p-error">{errors.state_id}</small>}
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="city_name" className="font-medium text-sm">City Name *</label>
            <InputText
              id="city_name"
              value={cityName}
              onChange={(e) => { setCityName(e.target.value); setErrors({ ...errors, city_name: '' }); }}
              placeholder="Enter city name"
              className={`w-full ${errors.city_name ? 'p-invalid' : ''}`}
            />
            {errors.city_name && <small className="p-error">{errors.city_name}</small>}
          </div>
        </div>
      </Dialog>

      {/* Import Excel Dialog */}
      <Dialog
        visible={showImportDialog}
        header="Import Cities from Excel"
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
              Download Template (City Name, State Name)
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
