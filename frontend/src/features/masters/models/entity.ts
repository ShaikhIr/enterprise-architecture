import type { PaginatedResponse } from './common';

export interface Entity {
  id: string;
  entity_name: string;
  short_code: string | null;
  company_code: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
}

export interface EntityListResponse extends PaginatedResponse<Entity> {}

export interface CreateEntityRequest {
  entity_name: string;
  short_code?: string;
  company_code?: string;
}

export interface UpdateEntityRequest {
  entity_name?: string;
  short_code?: string;
  company_code?: string;
  is_active?: boolean;
}

export interface EntityDropdownItem {
  id: string;
  label: string; // "{Short Code} - {Entity Name}"
}
