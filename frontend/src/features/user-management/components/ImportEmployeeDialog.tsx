/**
 * Import Employee Dialog.
 * Fetches employees from Darwin AD by IDs and upserts them into the system.
 */

import { useState } from 'react';

import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Tag } from 'primereact/tag';

import { extractApiError } from '@shared/utils/apiError';

import { useImportEmployees } from '../hooks/useUsers';
import type { ImportResult } from '../models/User';

/** Bounds the server enforces on a default password (bcrypt reads at most 72 bytes). */
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 72;

interface ImportEmployeeDialogProps {
  visible: boolean;
  onHide: () => void;
  onSuccess?: () => void;
}

export const ImportEmployeeDialog = ({ visible, onHide, onSuccess }: ImportEmployeeDialogProps) => {
  const [employeeIds, setEmployeeIds] = useState('');
  const [defaultPassword, setDefaultPassword] = useState('');
  const [results, setResults] = useState<ImportResult[] | null>(null);
  const importMutation = useImportEmployees();
  const [importError, setImportError] = useState<string | null>(null);

  const trimmedPassword = defaultPassword.trim();
  const passwordError =
    trimmedPassword.length > 0 &&
    (trimmedPassword.length < MIN_PASSWORD_LENGTH || trimmedPassword.length > MAX_PASSWORD_LENGTH)
      ? `Use ${MIN_PASSWORD_LENGTH} to ${MAX_PASSWORD_LENGTH} characters, or leave it blank.`
      : null;

  const handleImport = async () => {
    const ids = employeeIds
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean);

    if (ids.length === 0 || passwordError) return;

    setImportError(null);
    try {
      const response = await importMutation.mutateAsync({
        employeeIds: ids,
        defaultPassword: trimmedPassword || undefined,
      });
      setResults(response.results);
      if (response.created > 0 || response.updated > 0) {
        onSuccess?.();
      }
    } catch (err: unknown) {
      // Shown inside the dialog, next to the fields that may be the cause.
      setImportError(extractApiError(err, 'The import failed. Please try again.'));
    }
  };

  const handleClose = () => {
    setEmployeeIds('');
    setDefaultPassword('');
    setResults(null);
    setImportError(null);
    onHide();
  };

  const statusTemplate = (row: ImportResult) => {
    const severityMap: Record<string, 'success' | 'info' | 'danger'> = {
      created: 'success',
      updated: 'info',
      failed: 'danger',
    };
    return <Tag value={row.status} severity={severityMap[row.status] || 'info'} />;
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Close"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={handleClose}
      />
      {!results && (
        <Button
          label="Import"
          icon="pi pi-download"
          onClick={handleImport}
          loading={importMutation.isPending}
          disabled={!employeeIds.trim() || !!passwordError}
        />
      )}
    </div>
  );

  return (
    <Dialog
      header="Fetch & Import Employees"
      visible={visible}
      onHide={handleClose}
      style={{ width: '600px' }}
      footer={footer}
      modal
      aria-label="Import employees dialog"
    >
      <div className="flex flex-column gap-4 pt-2">
        {/* Input */}
        <div className="flex flex-column gap-2">
          <label htmlFor="import-ids" className="font-medium">
            Employee IDs (comma-separated)
          </label>
          <InputText
            id="import-ids"
            value={employeeIds}
            onChange={(e) => setEmployeeIds(e.target.value)}
            placeholder="e.g. 93300040, 93300041, 93300042"
            className="w-full"
            disabled={!!results}
            aria-label="Employee IDs to import"
          />
          <small className="text-600">
            Employees are imported with username = Employee ID. They sign in through the corporate
            directory, so leave the default password blank unless a local password is needed.
          </small>
        </div>

        {/* Optional default password for the newly created users */}
        <div className="flex flex-column gap-2">
          <label htmlFor="import-default-password" className="font-medium">
            Default Password (optional)
          </label>
          <Password
            id="import-default-password"
            value={defaultPassword}
            onChange={(e) => setDefaultPassword(e.target.value)}
            placeholder="Blank: a random password is set"
            invalid={!!passwordError}
            feedback={false}
            toggleMask
            className="w-full"
            inputClassName="w-full"
            disabled={!!results}
            aria-label="Default password for imported employees"
          />
          <small className="text-600">
            Applied only to newly created users. Existing users keep their current password.
            Left blank, each new user gets a random password nobody knows.
          </small>
          {passwordError && <small className="p-error">{passwordError}</small>}
        </div>

        {importError && (
          <small className="p-error" role="alert">
            {importError}
          </small>
        )}

        {/* Results table */}
        {results && (
          <div>
            <div className="flex align-items-center gap-3 mb-3">
              <Tag value={`Created: ${importMutation.data?.created || 0}`} severity="success" />
              <Tag value={`Updated: ${importMutation.data?.updated || 0}`} severity="info" />
              <Tag value={`Failed: ${importMutation.data?.failed || 0}`} severity="danger" />
            </div>
            <DataTable
              value={results}
              size="small"
              stripedRows
              paginator={results.length > 5}
              rows={5}
              emptyMessage="No results"
              aria-label="Import results"
            >
              <Column field="employee_id" header="Employee ID" />
              <Column header="Status" body={statusTemplate} />
              <Column field="message" header="Message" />
            </DataTable>
          </div>
        )}
      </div>
    </Dialog>
  );
};
