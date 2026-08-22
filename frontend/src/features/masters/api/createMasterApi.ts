/**
 * CRUD client factory for master data.
 *
 * All six masters expose an identical REST shape, so the HTTP mechanics live here
 * once. Only the mechanics are shared — each master declares its own request and
 * response types in its own `*Api.ts`, so the fields it accepts stay readable
 * from that file.
 */

import { apiClient } from '@shared/services/apiClient';

import type { MasterListParams, MasterPage } from '../models/common';

/** CRUD surface shared by every master, typed per entity. */
export interface MasterApi<TEntity, TCreate, TUpdate, TParams> {
  list: (params?: TParams) => Promise<MasterPage<TEntity>>;
  getById: (id: string) => Promise<TEntity>;
  create: (request: TCreate) => Promise<TEntity>;
  update: (id: string, request: TUpdate) => Promise<TEntity>;
  remove: (id: string) => Promise<void>;
}

/**
 * Build the CRUD client for one master.
 *
 * @param basePath Path under the API root, e.g. `/masters/countries`.
 * @param listKey  The key the list endpoint nests its rows under. Each master
 *                 names it after itself (`countries`, `categories_of_law`, ...),
 *                 so it must be supplied rather than derived from the path.
 */
export const createMasterApi = <TEntity, TCreate, TUpdate, TParams extends MasterListParams>(
  basePath: string,
  listKey: string,
): MasterApi<TEntity, TCreate, TUpdate, TParams> => ({
  list: async (params?: TParams): Promise<MasterPage<TEntity>> => {
    const { data } = await apiClient.get<Record<string, unknown>>(basePath, {
      params: { skip: 0, limit: 100, ...params },
    });
    // The only cast in the feature: the envelope key is dynamic, so it cannot be
    // expressed in the response type. Contained here instead of at every caller.
    return {
      items: (data[listKey] as TEntity[] | undefined) ?? [],
      total: Number(data.total ?? 0),
      skip: Number(data.skip ?? 0),
      limit: Number(data.limit ?? 0),
    };
  },

  getById: async (id: string): Promise<TEntity> => {
    const { data } = await apiClient.get<TEntity>(`${basePath}/${id}`);
    return data;
  },

  create: async (request: TCreate): Promise<TEntity> => {
    const { data } = await apiClient.post<TEntity>(basePath, request);
    return data;
  },

  update: async (id: string, request: TUpdate): Promise<TEntity> => {
    const { data } = await apiClient.patch<TEntity>(`${basePath}/${id}`, request);
    return data;
  },

  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`${basePath}/${id}`);
  },
});
