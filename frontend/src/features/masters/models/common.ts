/** Common types shared across all master entity modules */

export interface PaginatedParams {
  skip: number;
  limit: number;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  status?: string;
  [key: string]: unknown; // additional filters
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export interface DropdownOption {
  label: string;
  value: string;
}

export interface BulkUploadResponse {
  total: number;
  successful: number;
  failed: number;
  errors: Array<{ row: number; message: string }>;
}
