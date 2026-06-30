/**
 * State Master Page.
 * Full CRUD with PrimeReact DataTable, add/edit dialog with country dropdown,
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
import { stateApi, State } from '../api/stateApi';
import { countryApi, Country } from '../api/countryApi';

export const StateMasterPage = () => {
  const [states, setStates] = useState<State[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedCountryId, setSelectedCountryId] = useState<string | null>(null);
  const [languageKey, setLanguageKey] = useState('');
  const [stateName, setStateName] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useRef<Toast>(null);

  const loadStates = async () => {
    setLoading(true);
    try {
      const data = await stateApi.getStates(true);
      setStates(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load states' });
    } finally {
      setLoading(false);
    }
  };

  const loadCountries = async () => {
    try {
      const data = await countryApi.getCountries(false);
      setCountries(data);
    } catch {
      // Silent fail
    }
  };

  useEffect(() => {
    loadStates();
    loadCountries();
  }, []);

  const openNew = () => {
    setEditingId(null);
    setSelectedCountryId(null);
    setLanguageKey('');
    setStateName('');
    setErrors({});
    setShowDialog(true);
  };

  const editState = (state: State) => {
    setEditingId(state.id);
    setSelectedCountryId(state.country_id);
    setLanguageKey(state.language_key);
    setStateName(state.state_name);
    setErrors({});
    setShowDialog(true);
  };

  const saveState = async () => {
    const newErrors: Record<string, string> = {};
    if (!selectedCountryId) newErrors.country_id = 'Country is required';
    if (!languageKey.trim()) newErrors.language_key = 'Language key is required';
    if (!stateName.trim()) newErrors.state_name = 'State name is required';
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    try {
      if (editingId) {
        await stateApi.updateState(editingId, {
          country_id: selectedCountryId!,
          language_key: languageKey.trim(),
          state_name: stateName.trim(),
        });
      } else {
        await stateApi.createState({
          country_id: selectedCountryId!,
          language_key: languageKey.trim(),
          state_name: stateName.trim(),
        });
      }
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'State saved successfully' });
      setShowDialog(false);
      loadStates();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to save state';
      toast.current?.show({ severity: 'error', summary: 'Error', detail });
    }
  };

  const confirmDelete = (state: State) => {
    confirmDialog({
      message: `Are you sure you want to deactivate "${state.state_name}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await stateApi.deleteState(state.id);
          toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'State deactivated' });
          loadStates();
        } catch (err: any) {
          const detail = err.response?.data?.detail || 'Failed to deactivate state';
          toast.current?.show({ severity: 'error', summary: 'Error', detail });
        }
      },
    });
  };

  const downloadTemplate = async () => {
    try {
      await stateApi.downloadTemplate();
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template' });
    }
  };

  const importExcel = async () => {
    if (!importFile) return;
    try {
      const result = await stateApi.importExcel(importFile);
      toast.current?.show({
        severity: 'success',
        summary: 'Import Complete',
        detail: `Created: ${result.created}, Skipped: ${result.skipped}`,
      });
      setShowImportDialog(false);
      setImportFile(null);
      loadStates();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to import';
      toast.current?.show({ severity: 'error', summary: 'Import Failed', detail });
    }
  };

  const statusTemplate = (rowData: State) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'secondary' as any}
    />
  );

  const actionsTemplate = (rowData: State) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" text size="small" onClick={() => editState(rowData)} aria-label="Edit" />
      {rowData.is_active && (
        <Button icon="pi pi-trash" text severity="danger" size="small" onClick={() => confirmDelete(rowData)} aria-label="Deactivate" />
      )}
    </div>
  );

  const isFormValid = !!selectedCountryId && !!languageKey.trim() && !!stateName.trim();

  const dialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" text onClick={() => setShowDialog(false)} />
      <Button label="Save" onClick={saveState} disabled={!isFormValid} />
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
        <h2 className="m-0" style={{ color: 'var(--color-text-primary)' }}>State Master</h2>
        <div className="flex gap-2">
          <Button
            label="Import Excel"
            icon="pi pi-file-excel"
            severity="success"
            size="small"
            onClick={() => setShowImportDialog(true)}
          />
          <Button
            label="Add State"
            icon="pi pi-plus"
            size="small"
            onClick={openNew}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="card">
        <DataTable
          value={states}
          loading={loading}
          paginator
          rows={15}
          size="small"
          stripedRows
          emptyMessage="No states found"
          sortField="state_name"
          sortOrder={1}
        >
          <Column field="state_name" header="State Name" sortable />
          <Column field="country_name" header="Country" sortable body={(row) => row.country_name || '—'} />
          <Column field="language_key" header="Language Key" sortable style={{ width: '130px' }} />
          <Column header="Status" body={statusTemplate} style={{ width: '120px' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '120px' }} />
        </DataTable>
      </div>

      {/* Add/Edit Dialog */}
      <Dialog
        visible={showDialog}
        header={editingId ? 'Edit State' : 'Add New State'}
        modal
        style={{ width: '450px' }}
        footer={dialogFooter}
        onHide={() => setShowDialog(false)}
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-1">
            <label htmlFor="country_id" className="font-medium text-sm">Country *</label>
            <Dropdown
              id="country_id"
              value={selectedCountryId}
              onChange={(e) => { setSelectedCountryId(e.value); setErrors({ ...errors, country_id: '' }); }}
              options={countries}
              optionLabel="country_name"
              optionValue="id"
              filter
              placeholder="Select country"
              className={`w-full ${errors.country_id ? 'p-invalid' : ''}`}
            />
            {errors.country_id && <small className="p-error">{errors.country_id}</small>}
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="language_key" className="font-medium text-sm">Language Key *</label>
            <InputText
              id="language_key"
              value={languageKey}
              onChange={(e) => { setLanguageKey(e.target.value); setErrors({ ...errors, language_key: '' }); }}
              placeholder="e.g. EN, DE, FR"
              className={`w-full ${errors.language_key ? 'p-invalid' : ''}`}
            />
            {errors.language_key && <small className="p-error">{errors.language_key}</small>}
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="state_name" className="font-medium text-sm">State Name *</label>
            <InputText
              id="state_name"
              value={stateName}
              onChange={(e) => { setStateName(e.target.value); setErrors({ ...errors, state_name: '' }); }}
              placeholder="Enter state name"
              className={`w-full ${errors.state_name ? 'p-invalid' : ''}`}
            />
            {errors.state_name && <small className="p-error">{errors.state_name}</small>}
          </div>
        </div>
      </Dialog>

      {/* Import Excel Dialog */}
      <Dialog
        visible={showImportDialog}
        header="Import States from Excel"
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
              Download Template (Language Key, Country Name, State Name)
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
