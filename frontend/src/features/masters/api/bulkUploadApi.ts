/**
 * Bulk Upload API.
 * Handles file uploads for master entity bulk import and template downloads.
 */

import { apiClient } from '@shared/services/apiClient';
import type { BulkUploadResponse } from '../models/common';

export type BulkUploadEntityType =
  | 'vendor'
  | 'customer'
  | 'product_master'
  | 'product_detail'
  | 'agreement'
  | 'mapping';

export const bulkUploadApi = {
  /**
   * Upload a CSV/XLSX file for bulk import of a specific entity type.
   */
  upload: async (file: File, entityType: BulkUploadEntityType): Promise<BulkUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity_type', entityType);
    const { data } = await apiClient.post<BulkUploadResponse>('/bulk-upload', formData, {
      // Setting Content-Type to undefined lets Axios (and the browser) generate
      // the correct 'multipart/form-data; boundary=...' header automatically.
      // Manually specifying 'multipart/form-data' without a boundary causes
      // the server to fail parsing the request body.
      headers: { 'Content-Type': undefined as unknown as string },
    });
    return data;
  },

  /**
   * Get the download URL for the bulk upload template of a given entity type.
   */
  getTemplateUrl: (entityType: BulkUploadEntityType): string => {
    return `/api/v1/bulk-upload/template/${entityType}`;
  },
};
