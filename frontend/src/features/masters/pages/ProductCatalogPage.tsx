/**
 * ProductCatalogPage — Product Master management.
 *
 * The former two-level hierarchy (Product Master + Product Details tabs) has
 * been collapsed. This page now shows a single Product Master table with all
 * fields (basic_material_code, product_name, child_code, variant fields, etc.)
 *
 * Requirements: 5.1–5.9, 12.1, 12.5, 13.2
 */

import { useRef, useState } from 'react';
import { DataTable, type DataTablePageEvent, type DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { PermissionGate } from '@core/rbac/PermissionGate';
import { ProductMasterFormDialog } from '../components/ProductMasterFormDialog';
import { BulkUploadDialog } from '../components/BulkUploadDialog';
import {
  useProductMasters,
  useCreateProductMaster,
  useUpdateProductMaster,
} from '../hooks/useProductMasters';
import type { ProductMaster } from '../models/productMaster';
import type { PaginatedParams } from '../models/common';
import type { ProductMasterCreateFormData } from '../schemas/productMasterSchema';

export const ProductCatalogPage = () => {
  const toast = useRef<Toast>(null);

  const [page, setPage] = useState(0);
  const [rows, setRows] = useState(10);
  const [sortField, setSortField] = useState('product_name');
  const [sortOrder, setSortOrder] = useState<1 | -1>(1);
  const [filters, setFilters] = useState({
    basic_material_code: '',
    product_name: '',
    child_code: '',
  });
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editProductMaster, setEditProductMaster] = useState<ProductMaster | null>(null);
  const [showBulkUpload, setShowBulkUpload] = useState(false);

  const params: PaginatedParams = {
    skip: page * rows,
    limit: rows,
    sort_by: sortField,
    sort_order: sortOrder === 1 ? 'asc' : 'desc',
    ...(filters.basic_material_code && { basic_material_code: filters.basic_material_code }),
    ...(filters.product_name && { product_name: filters.product_name }),
    ...(filters.child_code && { child_code: filters.child_code }),
  };

  const { data, isLoading } = useProductMasters(params);
  const createMutation = useCreateProductMaster();
  const updateMutation = useUpdateProductMaster();

  const onPageChange = (e: DataTablePageEvent) => {
    setPage(e.page ?? 0);
    setRows(e.rows);
  };

  const onSort = (e: DataTableSortEvent) => {
    setSortField(e.sortField as string);
    setSortOrder(e.sortOrder as 1 | -1);
  };

  const handleFilterChange = (field: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [field]: value }));
    setPage(0);
  };

  const handleCreate = async (formData: ProductMasterCreateFormData) => {
    try {
      await createMutation.mutateAsync(formData);
      setShowCreateDialog(false);
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Product master created successfully', life: 3000 });
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 409) {
        toast.current?.show({ severity: 'error', summary: 'Conflict', detail: error.response?.data?.detail || 'A conflict occurred. The product master may already exist.', life: 5000 });
      } else if (status !== 422) {
        toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to create product master', life: 5000 });
      }
      throw error;
    }
  };

  const handleEdit = async (formData: ProductMasterCreateFormData) => {
    if (!editProductMaster) return;
    try {
      await updateMutation.mutateAsync({ id: editProductMaster.id, request: formData });
      setEditProductMaster(null);
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Product master updated successfully', life: 3000 });
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 409) {
        toast.current?.show({ severity: 'error', summary: 'Conflict', detail: error.response?.data?.detail || 'A conflict occurred. The product master may already exist.', life: 5000 });
      } else if (status !== 422) {
        toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to update product master', life: 5000 });
      }
      throw error;
    }
  };

  const toolbarLeft = (
    <div className="flex gap-2">
      <PermissionGate permission="product_master.create">
        <Button label="New Product" icon="pi pi-plus" onClick={() => setShowCreateDialog(true)} aria-label="Create new product master" />
      </PermissionGate>
      <PermissionGate permission="product_master.create">
        <Button label="Bulk Upload" icon="pi pi-upload" severity="secondary" outlined onClick={() => setShowBulkUpload(true)} aria-label="Bulk upload product masters" />
      </PermissionGate>
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Product Management</h2>
        <p className="text-600 mt-1 mb-0">Manage product master records</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3 p-0 border-none" start={toolbarLeft} />

        <DataTable
          value={data?.items ?? []}
          totalRecords={data?.total ?? 0}
          lazy paginator
          rows={rows}
          first={page * rows}
          onPage={onPageChange}
          onSort={onSort}
          sortField={sortField}
          sortOrder={sortOrder}
          loading={isLoading}
          rowsPerPageOptions={[10, 25, 50]}
          emptyMessage="No product masters found"
          filterDisplay="row"
          stripedRows
          size="small"
          aria-label="Product master data table"
        >
          <Column
            field="basic_material_code"
            header="Basic Material Code"
            sortable filter showFilterMenu={false}
            filterElement={
              <InputText value={filters.basic_material_code} onChange={(e) => handleFilterChange('basic_material_code', e.target.value)} placeholder="Search Material Code" className="w-full" aria-label="Filter by basic material code" />
            }
          />
          <Column
            field="product_name"
            header="Product Name"
            sortable filter showFilterMenu={false}
            filterElement={
              <InputText value={filters.product_name} onChange={(e) => handleFilterChange('product_name', e.target.value)} placeholder="Search Product Name" className="w-full" aria-label="Filter by product name" />
            }
          />
          <Column
            field="child_code"
            header="Child Code"
            sortable filter showFilterMenu={false}
            filterElement={
              <InputText value={filters.child_code} onChange={(e) => handleFilterChange('child_code', e.target.value)} placeholder="Search Child Code" className="w-full" aria-label="Filter by child code" />
            }
          />
          <Column field="variant_description" header="Variant Description" sortable />
          <Column field="hsn_code" header="HSN Code" sortable />
          <Column field="pack_size" header="Pack Size" sortable />
          <Column field="unit_of_measure" header="UoM" sortable />
          <Column field="mrp" header="MRP" sortable style={{ textAlign: 'right' }} />
          <Column field="rate" header="Rate" sortable style={{ textAlign: 'right' }} />
          <Column field="gst_percent" header="GST %" sortable style={{ textAlign: 'right' }} />
          <Column field="status" header="Status" sortable style={{ width: '120px' }}
            body={(row: ProductMaster) => (
              <Tag value={row.status === 'Active' ? 'Active' : 'Inactive'} severity={row.status === 'Active' ? 'success' : 'danger'} />
            )}
          />
          <Column header="Actions" style={{ width: '100px' }}
            body={(row: ProductMaster) => (
              <PermissionGate permission="product_master.update">
                <Button icon="pi pi-pencil" severity="secondary" text rounded onClick={() => setEditProductMaster(row)} aria-label={`Edit product master ${row.product_name}`} />
              </PermissionGate>
            )}
          />
        </DataTable>
      </div>

      <ProductMasterFormDialog visible={showCreateDialog} onHide={() => setShowCreateDialog(false)} productMaster={null} onSubmit={handleCreate} loading={createMutation.isPending} />
      <ProductMasterFormDialog visible={editProductMaster !== null} onHide={() => setEditProductMaster(null)} productMaster={editProductMaster} onSubmit={handleEdit} loading={updateMutation.isPending} />
      <BulkUploadDialog visible={showBulkUpload} onHide={() => setShowBulkUpload(false)} entityType="product_master" onSuccess={() => toast.current?.show({ severity: 'success', summary: 'Bulk Upload Complete', detail: 'Product masters have been uploaded successfully', life: 3000 })} />
    </div>
  );
};
