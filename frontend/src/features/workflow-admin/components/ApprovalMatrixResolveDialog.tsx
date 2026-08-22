/**
 * Routing preview.
 *
 * Rule configuration is only as good as what it does to real records, so this
 * dialog posts a sample payload to the read-only resolve endpoint and shows which
 * matrix would win. Nothing is written.
 */

import { useEffect, useState } from 'react';

import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Message } from 'primereact/message';
import { Tag } from 'primereact/tag';

import type { ApprovalResolveResponse } from '../models/ApprovalMatrix';

const SAMPLE = `{
  "amount": 250000,
  "state": { "code": "MH" }
}`;

interface ApprovalMatrixResolveDialogProps {
  visible: boolean;
  loading?: boolean;
  result?: ApprovalResolveResponse | null;
  onHide: () => void;
  onResolve: (entityType: string, entityData: Record<string, unknown>) => void;
}

export const ApprovalMatrixResolveDialog = ({
  visible,
  loading,
  result,
  onHide,
  onResolve,
}: ApprovalMatrixResolveDialogProps) => {
  const [entityType, setEntityType] = useState('');
  const [payload, setPayload] = useState(SAMPLE);
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setEntityType('');
    setPayload(SAMPLE);
    setParseError(null);
  }, [visible]);

  const run = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload);
    } catch {
      setParseError('Sample record must be valid JSON.');
      return;
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      setParseError('Sample record must be a JSON object.');
      return;
    }
    setParseError(null);
    onResolve(entityType.trim(), parsed as Record<string, unknown>);
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Close" icon="pi pi-times" severity="secondary" outlined onClick={onHide} />
      <Button
        label="Resolve"
        icon="pi pi-play"
        loading={loading}
        disabled={entityType.trim().length < 2}
        onClick={run}
      />
    </div>
  );

  return (
    <Dialog
      header="Preview Approval Routing"
      visible={visible}
      onHide={onHide}
      style={{ width: '620px' }}
      footer={footer}
      modal
      aria-label="Approval routing preview dialog"
    >
      <div className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="resolve-entity-type" className="font-medium">
            Entity Type
          </label>
          <InputText
            id="resolve-entity-type"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            placeholder="e.g. compliance_task"
          />
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="resolve-payload" className="font-medium">
            Sample Record (JSON)
          </label>
          <InputTextarea
            id="resolve-payload"
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            rows={7}
            className={parseError ? 'p-invalid font-mono' : 'font-mono'}
            aria-describedby="resolve-payload-error"
          />
          <small className="text-600">
            Dotted condition fields read into nested objects, so `state.code` matches the example
            below.
          </small>
          {parseError && (
            <small id="resolve-payload-error" className="p-error">
              {parseError}
            </small>
          )}
        </div>

        {result && !result.matched && (
          <Message
            severity="warn"
            text="No active matrix matched this record — it would route to nobody."
          />
        )}

        {result?.matched && result.matrix && (
          <div className="flex flex-column gap-2">
            <div className="flex align-items-center gap-2 flex-wrap">
              <Tag value="Matched" severity="success" />
              <span className="font-semibold">{result.matrix.name}</span>
              <span className="text-600">({result.matrix.code})</span>
              <span className="text-600">priority {result.matrix.priority}</span>
            </div>
            <DataTable
              value={result.assignments}
              size="small"
              stripedRows
              showGridlines
              emptyMessage="Matrix matched but defines no approval levels."
              aria-label="Resolved approvers table"
            >
              <Column
                header="Level"
                body={(row) => <Tag value={`L${row.level}`} severity="info" />}
                style={{ width: '6rem' }}
              />
              <Column field="assignment_type" header="Type" style={{ width: '7rem' }} />
              <Column header="Target" body={(row) => row.role_id ?? row.user_id ?? '—'} />
            </DataTable>
          </div>
        )}
      </div>
    </Dialog>
  );
};
