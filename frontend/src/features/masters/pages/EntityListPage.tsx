/**
 * Entity List Page.
 * Paginated DataTable with column-level search, Active Only toggle,
 * create/edit dialog integration, and RBAC-gated actions.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 12.1, 12.4, 12.5, 12.6, 12.7, 13.2, 14.5, 14.6, 16.2, 16.4
 */

import { useState, useRef } from 'react';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { PermissionGate } from '@core/rbac/PermissionGate';
import { EntityFormDialog } from '../components/EntityFormDialog';
import { useEntities, useCreateEntity, useUpdateEntity } from '../hooks/useEntities';
import type { Entity } from '../models/entity';
import type { PaginatedParams } from '../models/common';
import type { EntityCreateFormData } from '../schemas/entitySchema';

/**
 * Formats an entity for dropdown display.
 * Produces "{Short Code} - {Entity Name}" or "Unknown - {Entity Name}" when short_code is empty/null.
 */
export function formatEntityDropdown(entity: { short_code: string | null; entity_name: string }): string {
  const code = entity.short_code?.trim() ? entity.short_code.trim() : 'Unknown';
  return `${code} - ${entity.entity_name}`;
}

export const EntityListPage = () => {
  // Pagination & sorting state
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState(10);
  const [sortField, setSortField] = useState('entity_name');
  const [sortOrder, setSortOrder] = useState<1 | -1>(1);

  // Filter state
  const [filters, setFilters] = useState({
    entity_name: '',
    short_code: '',
    company_code: '',
  });

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editEntity, setEditEntity] = useState<Entity | null>(null);

  const toast = useRef<Toast>(null);

  // Build query params
  const params: PaginatedParams = {
    skip: page * rows,
    limit: rows,
    sort_by: sortField,
    sort_order: sortOrder === 1 ? 'asc' : 'desc',
    ...(filters.entity_name && { entity_name: filters.entity_name }),
    ...(filters.short_code && { short_code: filters.short_code }),
    ...(filters.company_code && { company_code: filters.company_code }),
  };

  const { data, isLoading } = useEntities(params);
  const createMutation = useCreateEntity();
  const updateMutation = useUpdateEntity();

  // Handlers
  const onPageChange = (event: DataTablePageEvent) => {
    setPage(event.page ?? 0);
    setRows(event.rows);
  };

  const onSort = (event: DataTableSortEvent) => {
    setSortField(event.sortField as string);
    setSortOrder(event.sortOrder as 1 | -1);
  };

  const handleFilterChange = (field: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [field]: value }));
    setPage(0); // reset to first page on filter change
  };

  const handleCreate = async (formData: EntityCreateFormData) => {
    try {
      await createMutation.mutateAsync(formData);
      setShowCreateDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Entity created successfully',
        life: 3000,
      });
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 409) {
        const detail = error.response?.data?.detail || 'A conflict occurred. The entity may already exist.';
        toast.current?.show({
          severity: 'error',
          summary: 'Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // 422 errors are mapped to inline form errors by EntityFormDialog
      } else {
        toast.current?.show({
          severity: 'error',
          summary: 'Error',
          detail: error.response?.data?.detail || 'Failed to create entity',
          life: 5000,
        });
      }
      throw error; // re-throw so the dialog's onSubmit can handle 422 inline errors
    }
  };

  const handleEdit = async (formData: EntityCreateFormData) => {
    if (!editEntity) return;
    try {
      await updateMutation.mutateAsync({ id: editEntity.id, request: formData });
      setEditEntity(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'Entity updated successfully',
        life: 3000,
      });
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 409) {
        const detail = error.response?.data?.detail || 'A conflict occurred. The entity may already exist.';
        toast.current?.show({
          severity: 'error',
          summary: 'Conflict',
          detail,
          life: 5000,
        });
      } else if (status === 422) {
        // 422 errors mapped to inline form errors by EntityFormDialog
      } else {
        toast.current?.show({
          severity: 'error',
          summary: 'Error',
          detail: error.response?.data?.detail || 'Failed to update entity',
          life: 5000,
        });
      }
      throw error;
    }
  };

  // Column templates
  const statusBodyTemplate = (rowData: Entity) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'danger'}
    />
  );

  const actionsBodyTemplate = (rowData: Entity) => (
    <PermissionGate permission="entity.update">
      <Button
        icon="pi pi-pencil"
        severity="secondary"
        text
        rounded
        onClick={() => setEditEntity(rowData)}
        aria-label={`Edit entity ${rowData.entity_name}`}
      />
    </PermissionGate>
  );

  // Column filter header templates
  const entityNameFilterTemplate = () => (
    <InputText
      value={filters.entity_name}
      onChange={(e) => handleFilterChange('entity_name', e.target.value)}
      placeholder="Search Entity Name"
      className="w-full"
      aria-label="Filter by entity name"
    />
  );

  const shortCodeFilterTemplate = () => (
    <InputText
      value={filters.short_code}
      onChange={(e) => handleFilterChange('short_code', e.target.value)}
      placeholder="Search Short Code"
      className="w-full"
      aria-label="Filter by short code"
    />
  );

  const companyCodeFilterTemplate = () => (
    <InputText
      value={filters.company_code}
      onChange={(e) => handleFilterChange('company_code', e.target.value)}
      placeholder="Search Company Code"
      className="w-full"
      aria-label="Filter by company code"
    />
  );

  // ─── Toolbar ────────────────────────────────────────────────────────────────
  const toolbarLeftContent = (
    <PermissionGate permission="entity.create">
      <Button
        label="New Entity"
        icon="pi pi-plus"
        onClick={() => setShowCreateDialog(true)}
        aria-label="Create new entity"
      />
    </PermissionGate>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Entity Master</h2>
        <p className="text-600 mt-1 mb-0">Manage legal company entities</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
          <Toolbar className="mb-3 p-0 border-none" start={toolbarLeftContent} />
          <DataTable
            value={data?.items ?? []}
            totalRecords={data?.total ?? 0}
            lazy
            paginator
            rows={rows}
            first={page * rows}
            onPage={onPageChange}
            onSort={onSort}
            sortField={sortField}
            sortOrder={sortOrder}
            loading={isLoading}
            rowsPerPageOptions={[10, 25, 50]}
            emptyMessage="No entities found"
            filterDisplay="row"
            stripedRows
            size="small"
            aria-label="Entity master data table"
          >
            <Column
              field="entity_name"
              header="Entity Name"
              sortable
              filter
              filterElement={entityNameFilterTemplate}
              showFilterMenu={false}
            />
            <Column
              field="short_code"
              header="Short Code"
              sortable
              filter
              filterElement={shortCodeFilterTemplate}
              showFilterMenu={false}
            />
            <Column
              field="company_code"
              header="Company Code"
              sortable
              filter
              filterElement={companyCodeFilterTemplate}
              showFilterMenu={false}
            />
            <Column
              field="is_active"
              header="Status"
              body={statusBodyTemplate}
              sortable
              style={{ width: '120px' }}
            />
            <Column
              header="Actions"
              body={actionsBodyTemplate}
              style={{ width: '100px' }}
            />
          </DataTable>
      </div>

      {/* Create Entity Dialog */}
      <EntityFormDialog
        visible={showCreateDialog}
        onHide={() => setShowCreateDialog(false)}
        entity={null}
        onSubmit={handleCreate}
        loading={createMutation.isPending}
      />

      {/* Edit Entity Dialog */}
      <EntityFormDialog
        visible={editEntity !== null}
        onHide={() => setEditEntity(null)}
        entity={editEntity}
        onSubmit={handleEdit}
        loading={updateMutation.isPending}
      />
    </div>
  );
};
