/**
 * Country Master Page.
 * Full CRUD with PrimeReact DataTable, add/edit dialog with region dropdown,
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
import { countryApi, Country } from '../api/countryApi';
import { regionApi, Region } from '../api/regionApi';

export const CountryMasterPage = () => {
  const [countries, setCountries] = useState<Country[]>([]);
  const [regions, setRegions] = useState<Region[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [countryCode, setCountryCode] = useState('');
  const [countryName, setCountryName] = useState('');
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [codeError, setCodeError] = useState('');
  const [nameError, setNameError] = useState('');
  const toast = useRef<Toast>(null);

  const loadCountries = async () => {
    setLoading(true);
    try {
      const data = await countryApi.getCountries(true);
      setCountries(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load countries' });
    } finally {
      setLoading(false);
    }
  };

  const loadRegions = async () => {
    try {
      const data = await regionApi.getRegions(false);
      setRegions(data);
    } catch {
      // Silent fail for region dropdown
    }
  };

  useEffect(() => {
    loadCountries();
    loadRegions();
  }, []);

  const openNew = () => {
    setEditingId(null);
    setCountryCode('');
    setCountryName('');
    setSelectedRegionId(null);
    setCodeError('');
    setNameError('');
    setShowDialog(true);
  };

  const editCountry = (country: Country) => {
    setEditingId(country.id);
    setCountryCode(country.country_code);
    setCountryName(country.country_name);
    setSelectedRegionId(country.region_id);
    setCodeError('');
    setNameError('');
    setShowDialog(true);
  };

  const saveCountry = async () => {
    let hasError = false;
    if (!countryCode.trim()) {
      setCodeError('Country code is required');
      hasError = true;
    }
    if (!countryName.trim()) {
      setNameError('Country name is required');
      hasError = true;
    }
    if (hasError) return;

    try {
      if (editingId) {
        await countryApi.updateCountry(editingId, {
          country_code: countryCode.trim(),
          country_name: countryName.trim(),
          region_id: selectedRegionId,
        });
      } else {
        await countryApi.createCountry({
          country_code: countryCode.trim(),
          country_name: countryName.trim(),
          region_id: selectedRegionId,
        });
      }
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Country saved successfully' });
      setShowDialog(false);
      loadCountries();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to save country';
      toast.current?.show({ severity: 'error', summary: 'Error', detail });
    }
  };

  const confirmDelete = (country: Country) => {
    confirmDialog({
      message: `Are you sure you want to deactivate country "${country.country_name}"?`,
      header: 'Confirm Deactivation',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await countryApi.deleteCountry(country.id);
          toast.current?.show({ severity: 'success', summary: 'Deactivated', detail: 'Country deactivated' });
          loadCountries();
        } catch (err: any) {
          const detail = err.response?.data?.detail || 'Failed to deactivate country';
          toast.current?.show({ severity: 'error', summary: 'Error', detail });
        }
      },
    });
  };

  const downloadTemplate = async () => {
    try {
      await countryApi.downloadTemplate();
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to download template' });
    }
  };

  const importExcel = async () => {
    if (!importFile) return;
    try {
      const result = await countryApi.importExcel(importFile);
      toast.current?.show({
        severity: 'success',
        summary: 'Import Complete',
        detail: `Created: ${result.created}, Skipped: ${result.skipped}`,
      });
      setShowImportDialog(false);
      setImportFile(null);
      loadCountries();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to import';
      toast.current?.show({ severity: 'error', summary: 'Import Failed', detail });
    }
  };

  // Column templates
  const statusTemplate = (rowData: Country) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'secondary' as any}
    />
  );

  const actionsTemplate = (rowData: Country) => (
    <div className="flex gap-1">
      <Button icon="pi pi-pencil" text size="small" onClick={() => editCountry(rowData)} aria-label="Edit" />
      {rowData.is_active && (
        <Button icon="pi pi-trash" text severity="danger" size="small" onClick={() => confirmDelete(rowData)} aria-label="Deactivate" />
      )}
    </div>
  );

  const dialogFooter = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" text onClick={() => setShowDialog(false)} />
      <Button label="Save" onClick={saveCountry} disabled={!countryCode.trim() || !countryName.trim()} />
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
        <h2 className="m-0" style={{ color: 'var(--color-text-primary)' }}>Country Master</h2>
        <div className="flex gap-2">
          <Button
            label="Import Excel"
            icon="pi pi-file-excel"
            severity="success"
            size="small"
            onClick={() => setShowImportDialog(true)}
          />
          <Button
            label="Add Country"
            icon="pi pi-plus"
            size="small"
            onClick={openNew}
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="card">
        <DataTable
          value={countries}
          loading={loading}
          paginator
          rows={15}
          size="small"
          stripedRows
          emptyMessage="No countries found"
          sortField="country_name"
          sortOrder={1}
        >
          <Column field="country_code" header="Country Code" sortable style={{ width: '130px' }} />
          <Column field="country_name" header="Country Name" sortable />
          <Column field="region_name" header="Region" sortable body={(row) => row.region_name || '—'} />
          <Column header="Status" body={statusTemplate} style={{ width: '120px' }} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '120px' }} />
        </DataTable>
      </div>

      {/* Add/Edit Dialog */}
      <Dialog
        visible={showDialog}
        header={editingId ? 'Edit Country' : 'Add New Country'}
        modal
        style={{ width: '450px' }}
        footer={dialogFooter}
        onHide={() => setShowDialog(false)}
      >
        <div className="flex flex-column gap-3 pt-2">
          <div className="flex flex-column gap-1">
            <label htmlFor="country_code" className="font-medium text-sm">Country Code *</label>
            <InputText
              id="country_code"
              value={countryCode}
              onChange={(e) => { setCountryCode(e.target.value); setCodeError(''); }}
              placeholder="e.g. US, IN, DE"
              className={`w-full ${codeError ? 'p-invalid' : ''}`}
            />
            {codeError && <small className="p-error">{codeError}</small>}
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="country_name" className="font-medium text-sm">Country Name *</label>
            <InputText
              id="country_name"
              value={countryName}
              onChange={(e) => { setCountryName(e.target.value); setNameError(''); }}
              placeholder="Enter country name"
              className={`w-full ${nameError ? 'p-invalid' : ''}`}
            />
            {nameError && <small className="p-error">{nameError}</small>}
          </div>
          <div className="flex flex-column gap-1">
            <label htmlFor="region_id" className="font-medium text-sm">Region</label>
            <Dropdown
              id="region_id"
              value={selectedRegionId}
              onChange={(e) => setSelectedRegionId(e.value)}
              options={regions}
              optionLabel="region_name"
              optionValue="id"
              showClear
              placeholder="Select a region"
              className="w-full"
            />
          </div>
        </div>
      </Dialog>

      {/* Import Excel Dialog */}
      <Dialog
        visible={showImportDialog}
        header="Import Countries from Excel"
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
              Download Template (Country Code, Country Name, Region Name)
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
