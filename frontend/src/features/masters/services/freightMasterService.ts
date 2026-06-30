/**
 * Freight Masters API service.
 * Centralized service for all freight master data CRUD operations.
 */

import { apiClient } from '@shared/services/apiClient';

// ============================================================
// Types
// ============================================================

export interface Rate {
  id: string;
  rate: number;
  valid_from: string | null;
  valid_till: string | null;
  is_active: boolean;
}

export interface Country {
  id: string;
  country_name: string;
  country_code: string;
  is_active: boolean;
}

export interface City {
  id: string;
  city_name: string;
  country_id: string | null;
  is_active: boolean;
}

export interface AirMaster {
  id: string;
  to_country_id: string;
  country_code: string | null;
  country_name: string | null;
  product_type: string | null;
  min_slab: number;
  max_slab: number;
  slab_name: string | null;
  rates: Rate[];
  is_active: boolean;
}

export interface SeaMaster {
  id: string;
  to_country_id: string;
  country_code: string | null;
  country_name: string | null;
  product_type: string | null;
  slab_name: string | null;
  currency: string | null;
  rates: Rate[];
  is_active: boolean;
}

export interface SeaCbm {
  id: string;
  slab_name: string | null;
  from_cbm: number;
  to_cbm: number;
  type: string | null;
  total_count: number | null;
  is_active: boolean;
}

export interface VehicleType {
  id: string;
  from_no_of_pallet_or_box: number;
  to_no_of_pallet_or_box: number;
  vehicle_type: string;
  is_active: boolean;
}

export interface LocalMaster {
  id: string;
  from_city_id: string;
  from_city_name: string | null;
  to_city_id: string;
  to_city_name: string | null;
  product_type: string | null;
  vehicle_type_id: string | null;
  vehicle_type_name: string | null;
  min_slab: string | null;
  max_slab: string | null;
  rates: Rate[];
  is_active: boolean;
}

// ============================================================
// Country Master
// ============================================================

export const countryService = {
  list: (includeInactive = false) =>
    apiClient.get<Country[]>('/freight-masters/countries', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { country_name: string; country_code: string }) =>
    apiClient.post<Country>('/freight-masters/countries', data),

  update: (id: string, data: Partial<Omit<Country, 'id'>>) =>
    apiClient.put<Country>(`/freight-masters/countries/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/countries/${id}`),
};

// ============================================================
// City Master
// ============================================================

export const cityService = {
  list: (includeInactive = false) =>
    apiClient.get<City[]>('/freight-masters/cities', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { city_name: string; country_id?: string }) =>
    apiClient.post<City>('/freight-masters/cities', data),

  update: (id: string, data: Partial<Omit<City, 'id'>>) =>
    apiClient.put<City>(`/freight-masters/cities/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/cities/${id}`),
};

// ============================================================
// Air Master
// ============================================================

export const airMasterService = {
  list: (includeInactive = false) =>
    apiClient.get<AirMaster[]>('/freight-masters/air-masters', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { to_country_id: string; product_type?: string; min_slab: number; max_slab: number }) =>
    apiClient.post<AirMaster>('/freight-masters/air-masters', data),

  update: (id: string, data: Partial<Omit<AirMaster, 'id' | 'rates' | 'country_code' | 'country_name' | 'slab_name'>>) =>
    apiClient.put<AirMaster>(`/freight-masters/air-masters/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/air-masters/${id}`),

  addRate: (masterId: string, data: { rate: number; valid_from: string; valid_till: string }) =>
    apiClient.post<Rate>(`/freight-masters/air-masters/${masterId}/rates`, data),

  deleteRate: (rateId: string) =>
    apiClient.delete(`/freight-masters/air-masters/rates/${rateId}`),

  importExcel: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/freight-masters/air-master-import', formData);
  },

  downloadTemplate: () =>
    apiClient.get('/freight-masters/air-master-template', { responseType: 'blob' }),
};

// ============================================================
// Sea Master
// ============================================================

export const seaMasterService = {
  list: (includeInactive = false) =>
    apiClient.get<SeaMaster[]>('/freight-masters/sea-masters', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: { to_country_id: string; product_type?: string; slab_name?: string; currency?: string }) =>
    apiClient.post<SeaMaster>('/freight-masters/sea-masters', data),

  update: (id: string, data: Partial<Omit<SeaMaster, 'id' | 'rates' | 'country_code' | 'country_name'>>) =>
    apiClient.put<SeaMaster>(`/freight-masters/sea-masters/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/sea-masters/${id}`),

  addRate: (masterId: string, data: { rate: number; valid_from: string; valid_till: string }) =>
    apiClient.post<Rate>(`/freight-masters/sea-masters/${masterId}/rates`, data),

  deleteRate: (rateId: string) =>
    apiClient.delete(`/freight-masters/sea-masters/rates/${rateId}`),

  importExcel: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/freight-masters/sea-master-import', formData);
  },

  downloadTemplate: () =>
    apiClient.get('/freight-masters/sea-master-template', { responseType: 'blob' }),
};

// ============================================================
// Sea CBM Master
// ============================================================

export const seaCbmService = {
  list: (includeInactive = false) =>
    apiClient.get<SeaCbm[]>('/freight-masters/sea-cbm', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: Omit<SeaCbm, 'id' | 'is_active'>) =>
    apiClient.post<SeaCbm>('/freight-masters/sea-cbm', data),

  update: (id: string, data: Partial<Omit<SeaCbm, 'id'>>) =>
    apiClient.put<SeaCbm>(`/freight-masters/sea-cbm/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/sea-cbm/${id}`),

  importExcel: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/freight-masters/sea-cbm-import', formData);
  },

  downloadTemplate: () =>
    apiClient.get('/freight-masters/sea-cbm-template', { responseType: 'blob' }),
};

// ============================================================
// Vehicle Type Master
// ============================================================

export const vehicleTypeService = {
  list: (includeInactive = false) =>
    apiClient.get<VehicleType[]>('/freight-masters/vehicle-types', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: Omit<VehicleType, 'id' | 'is_active'>) =>
    apiClient.post<VehicleType>('/freight-masters/vehicle-types', data),

  update: (id: string, data: Partial<Omit<VehicleType, 'id'>>) =>
    apiClient.put<VehicleType>(`/freight-masters/vehicle-types/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/vehicle-types/${id}`),
};

// ============================================================
// Local Master
// ============================================================

export const localMasterService = {
  list: (includeInactive = false) =>
    apiClient.get<LocalMaster[]>('/freight-masters/local-masters', {
      params: { include_inactive: includeInactive },
    }),

  create: (data: {
    from_city_id: string;
    to_city_id: string;
    product_type?: string;
    vehicle_type_id?: string;
    min_slab?: string;
    max_slab?: string;
  }) => apiClient.post<LocalMaster>('/freight-masters/local-masters', data),

  update: (id: string, data: Partial<Omit<LocalMaster, 'id' | 'rates' | 'from_city_name' | 'to_city_name' | 'vehicle_type_name'>>) =>
    apiClient.put<LocalMaster>(`/freight-masters/local-masters/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/freight-masters/local-masters/${id}`),

  addRate: (masterId: string, data: { rate: number; valid_from: string; valid_till: string }) =>
    apiClient.post<Rate>(`/freight-masters/local-masters/${masterId}/rates`, data),

  deleteRate: (rateId: string) =>
    apiClient.delete(`/freight-masters/local-masters/rates/${rateId}`),

  importExcel: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/freight-masters/local-master-import', formData);
  },

  downloadTemplate: () =>
    apiClient.get('/freight-masters/local-master-template', { responseType: 'blob' }),
};
