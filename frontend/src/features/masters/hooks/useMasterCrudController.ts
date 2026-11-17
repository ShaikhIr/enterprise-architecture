/**
 * Dialog, toast and confirm wiring shared by the six master screens.
 *
 * Every master screen does the same four things — open a create dialog, open an
 * edit dialog, save, confirm-then-delete — so that behaviour lives here and the
 * pages are left holding only their columns and their form.
 *
 * Delete is worth noting: the master tables use ON DELETE RESTRICT, so removing a
 * country that still has states comes back as a 409 with a reason. That message is
 * surfaced verbatim rather than replaced with a generic failure, because "3
 * state(s) reference it" is the only useful thing to tell the user.
 */

import { useCallback, useRef, useState } from 'react';

import { confirmDialog } from 'primereact/confirmdialog';
import type { Toast } from 'primereact/toast';

import { extractApiError } from '@shared/utils/apiError';

import type { AuditedRecord } from '../models/common';

export interface MasterCrudControllerArgs<TEntity extends AuditedRecord, TCreate> {
  /** Singular, human-readable entity name, e.g. "Country". */
  entityLabel: string;
  /** How to name one row in a toast or confirmation. */
  labelOf: (row: TEntity) => string;
  onCreate: (data: TCreate) => Promise<unknown>;
  onUpdate: (id: number, data: TCreate) => Promise<unknown>;
  onDelete: (id: number) => Promise<unknown>;
}

export interface MasterCrudController<TEntity extends AuditedRecord, TCreate> {
  toast: React.RefObject<Toast | null>;
  dialogVisible: boolean;
  editing: TEntity | null;
  openCreate: () => void;
  openEdit: (row: TEntity) => void;
  closeDialog: () => void;
  submit: (data: TCreate) => Promise<void>;
  requestDelete: (row: TEntity) => void;
}

export const useMasterCrudController = <TEntity extends AuditedRecord, TCreate>({
  entityLabel,
  labelOf,
  onCreate,
  onUpdate,
  onDelete,
}: MasterCrudControllerArgs<TEntity, TCreate>): MasterCrudController<TEntity, TCreate> => {
  const toast = useRef<Toast | null>(null);
  const [dialogVisible, setDialogVisible] = useState(false);
  const [editing, setEditing] = useState<TEntity | null>(null);

  const notifyError = useCallback((error: unknown, fallback: string) => {
    toast.current?.show({
      severity: 'error',
      summary: 'Error',
      detail: extractApiError(error, fallback),
      life: 6000,
    });
  }, []);

  const notifySuccess = useCallback((summary: string, detail: string) => {
    toast.current?.show({ severity: 'success', summary, detail, life: 3000 });
  }, []);

  const openCreate = useCallback(() => {
    setEditing(null);
    setDialogVisible(true);
  }, []);

  const openEdit = useCallback((row: TEntity) => {
    setEditing(row);
    setDialogVisible(true);
  }, []);

  const closeDialog = useCallback(() => {
    setDialogVisible(false);
    setEditing(null);
  }, []);

  const submit = useCallback(
    async (data: TCreate) => {
      try {
        if (editing) {
          await onUpdate(editing.id, data);
          notifySuccess('Updated', `${entityLabel} '${labelOf(editing)}' updated`);
        } else {
          await onCreate(data);
          notifySuccess('Created', `${entityLabel} created`);
        }
        closeDialog();
      } catch (error) {
        notifyError(error, `Failed to save the ${entityLabel.toLowerCase()}`);
      }
    },
    [editing, onCreate, onUpdate, entityLabel, labelOf, notifySuccess, notifyError, closeDialog],
  );

  const requestDelete = useCallback(
    (row: TEntity) => {
      confirmDialog({
        header: `Delete ${entityLabel.toLowerCase()}`,
        message: `Delete '${labelOf(row)}'? Records still referenced by other master data cannot be deleted — deactivate them instead.`,
        icon: 'pi pi-exclamation-triangle',
        acceptLabel: 'Delete',
        acceptClassName: 'p-button-danger',
        rejectLabel: 'Cancel',
        accept: async () => {
          try {
            await onDelete(row.id);
            notifySuccess('Deleted', `${entityLabel} '${labelOf(row)}' deleted`);
          } catch (error) {
            notifyError(error, `Failed to delete the ${entityLabel.toLowerCase()}`);
          }
        },
      });
    },
    [entityLabel, labelOf, onDelete, notifySuccess, notifyError],
  );

  return {
    toast,
    dialogVisible,
    editing,
    openCreate,
    openEdit,
    closeDialog,
    submit,
    requestDelete,
  };
};
