/**
 * Bulk Upload Dialog.
 * Reusable dialog component for uploading CSV/XLSX files for any master entity type.
 * Displays upload progress, results summary, and row-level errors.
 */

import { useState, useRef } from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { bulkUploadApi, type BulkUploadEntityType } from '../api/bulkUploadApi';
import type { BulkUploadResponse } from '../models/common';

interface BulkUploadDialogProps {
  visible: boolean;
  onHide: () => void;
  entityType: BulkUploadEntityType;
  onSuccess: () => void;
}

const ACCEPTED_FILE_TYPES = '.csv,.xlsx';

const ENTITY_LABELS: Record<BulkUploadEntityType, string> = {
  vendor: 'Vendor',
  customer: 'Customer',
  product_master: 'Product Master',
  product_detail: 'Product Detail',
  agreement: 'Agreement',
  mapping: 'Mapping',
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const BulkUploadDialog = ({ visible, onHide, entityType, onSuccess }: BulkUploadDialogProps) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<BulkUploadResponse | null>(null);
  const [uploadSucceeded, setUploadSucceeded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toastRef = useRef<Toast>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setResults(null);
    setUploadSucceeded(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    try {
      const response = await bulkUploadApi.upload(selectedFile, entityType);
      setResults(response);
      setUploadSucceeded(response.successful > 0);
    } catch (error: unknown) {
      // Malformed file or server error — show Toast without results panel
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Upload failed. Please check the file format and try again.';
      toastRef.current?.show({
        severity: 'error',
        summary: 'Upload Error',
        detail: message,
        life: 5000,
      });
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    if (uploadSucceeded) {
      onSuccess();
    }
    resetState();
    onHide();
  };

  const resetState = () => {
    setSelectedFile(null);
    setResults(null);
    setUploading(false);
    setUploadSucceeded(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const templateUrl = bulkUploadApi.getTemplateUrl(entityType);

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
          label="Upload"
          icon="pi pi-upload"
          onClick={handleUpload}
          loading={uploading}
          disabled={!selectedFile || uploading}
        />
      )}
    </div>
  );

  return (
    <>
      <Toast ref={toastRef} />
      <Dialog
        header={`Bulk Upload — ${ENTITY_LABELS[entityType]}`}
        visible={visible}
        onHide={handleClose}
        style={{ width: '650px' }}
        footer={footer}
        modal
        aria-label={`Bulk upload dialog for ${ENTITY_LABELS[entityType]}`}
      >
        <div className="flex flex-column gap-4 pt-2">
          {/* Template download link */}
          <div className="flex align-items-center gap-2">
            <i className="pi pi-download text-primary" />
            <a
              href={templateUrl}
              download
              className="text-primary no-underline hover:underline"
              aria-label={`Download ${ENTITY_LABELS[entityType]} template`}
            >
              Download Template ({ENTITY_LABELS[entityType]})
            </a>
          </div>

          {/* File input */}
          {!results && (
            <div className="flex flex-column gap-2">
              <label htmlFor="bulk-upload-file" className="font-medium">
                Select File (CSV or XLSX)
              </label>
              <input
                ref={fileInputRef}
                id="bulk-upload-file"
                type="file"
                accept={ACCEPTED_FILE_TYPES}
                onChange={handleFileChange}
                disabled={uploading}
                className="w-full"
                aria-label="Select file for bulk upload"
              />
              {selectedFile && (
                <small className="text-600">
                  {selectedFile.name} — {formatFileSize(selectedFile.size)}
                </small>
              )}
            </div>
          )}

          {/* Progress spinner */}
          {uploading && (
            <div className="flex align-items-center justify-content-center gap-3 py-4">
              <ProgressSpinner
                style={{ width: '40px', height: '40px' }}
                strokeWidth="4"
                aria-label="Upload in progress"
              />
              <span className="text-600 font-medium">Processing...</span>
            </div>
          )}

          {/* Results summary */}
          {results && (
            <div className="flex flex-column gap-3">
              <div className="flex align-items-center gap-3">
                <Tag value={`Total: ${results.total}`} severity="info" />
                <Tag value={`Successful: ${results.successful}`} severity="success" />
                <Tag value={`Failed: ${results.failed}`} severity="danger" />
              </div>

              {/* Error table for row-level errors */}
              {results.errors.length > 0 && (
                <div>
                  <p className="font-medium mb-2 text-red-600">Row-level Errors:</p>
                  <DataTable
                    value={results.errors}
                    size="small"
                    stripedRows
                    scrollable
                    scrollHeight="250px"
                    emptyMessage="No errors"
                    aria-label="Bulk upload error details"
                  >
                    <Column field="row" header="Row" style={{ width: '80px' }} />
                    <Column field="message" header="Error Message" />
                  </DataTable>
                </div>
              )}
            </div>
          )}
        </div>
      </Dialog>
    </>
  );
};
