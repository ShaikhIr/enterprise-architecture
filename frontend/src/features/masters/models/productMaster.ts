import type { PaginatedResponse } from './common';

export type ProductStatus = 'Active' | 'Inactive';

/**
 * Product Master — merged from the former product_master + product_details
 * two-level hierarchy. Every row now carries both the base-product identity
 * fields (basic_material_code, product_name) and the SKU/variant fields.
 */
export interface ProductMaster {
  id: string;
  basic_material_code: string;
  product_name: string;
  child_code: string;
  variant_description: string | null;
  hsn_code: string | null;
  pack_size: string | null;
  unit_of_measure: string | null;
  mrp: number | null;
  rate: number | null;
  gst_percent: number | null;
  status: ProductStatus;
  created_date: string;
  modified_date: string;
  created_by: string | null;
  modified_by: string | null;
}

export interface ProductMasterListResponse extends PaginatedResponse<ProductMaster> {}

export interface CreateProductMasterRequest {
  basic_material_code: string;
  product_name: string;
  child_code: string;
  variant_description?: string;
  hsn_code?: string;
  pack_size?: string;
  unit_of_measure?: string;
  mrp?: number;
  rate?: number;
  gst_percent?: number;
}

export interface UpdateProductMasterRequest extends Partial<Omit<CreateProductMasterRequest, 'child_code'>> {
  child_code?: string;
  status?: ProductStatus;
}
