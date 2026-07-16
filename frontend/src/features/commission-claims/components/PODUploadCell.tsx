/**
 * PODUploadCell — Per-line POD document upload button for the ClaimLineTable.
 * Shows a checkmark + "Uploaded" label if pod_document_id is already set (Req 5.1, 5.3).
 * Triggers a hidden file input on click and calls onUpload with the selected File.
 */
import { useRef } from 'react';
import { Button } from 'primereact/button';
import { Tooltip } from 'primereact/tooltip';

interface PODUploadCellProps {
  lineId: string;
  podDocumentId: string | null;
  onUpload: (lineId: string, file: File) => void;
  disabled?: boolean;
}

export const PODUploadCell = ({
  lineId,
  podDocumentId,
  onUpload,
  disabled = false,
}: PODUploadCellProps) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(lineId, file);
      // Reset so the same file can be re-uploaded if needed
      e.target.value = '';
    }
  };

  return (
    <div className="flex align-items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png"
        style={{ display: 'none' }}
        onChange={handleChange}
        aria-label={`Upload POD for line ${lineId}`}
      />

      {podDocumentId ? (
        <>
          <span
            className={`pod-status-${lineId} flex align-items-center gap-1 text-green-600`}
            data-pr-tooltip="POD uploaded"
          >
            <i className="pi pi-check-circle" />
            <span className="text-sm">Uploaded</span>
          </span>
          <Tooltip target={`.pod-status-${lineId}`} />
          <Button
            icon="pi pi-refresh"
            size="small"
            text
            severity="secondary"
            onClick={handleClick}
            disabled={disabled}
            aria-label={`Replace POD document for line ${lineId}`}
            tooltip="Replace POD"
            tooltipOptions={{ position: 'top' }}
          />
        </>
      ) : (
        <Button
          label="Upload POD"
          icon="pi pi-upload"
          size="small"
          outlined
          onClick={handleClick}
          disabled={disabled}
          aria-label={`Upload POD document for line ${lineId}`}
        />
      )}
    </div>
  );
};
