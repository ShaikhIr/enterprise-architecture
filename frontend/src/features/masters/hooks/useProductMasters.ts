import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { productMasterApi } from '../api/productMasterApi';
import type { PaginatedParams } from '../models/common';
import type { UpdateProductMasterRequest } from '../models/productMaster';

const PRODUCT_MASTERS_KEY = ['product-masters'];

export const useProductMasters = (params: PaginatedParams) => {
  return useQuery({
    queryKey: [...PRODUCT_MASTERS_KEY, params],
    queryFn: () => productMasterApi.list(params),
    staleTime: 30_000,
  });
};

export const useCreateProductMaster = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: productMasterApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PRODUCT_MASTERS_KEY }),
  });
};

export const useUpdateProductMaster = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateProductMasterRequest }) =>
      productMasterApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PRODUCT_MASTERS_KEY }),
  });
};
