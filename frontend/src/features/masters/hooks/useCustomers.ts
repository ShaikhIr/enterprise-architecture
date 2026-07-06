import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customerApi } from '../api/customerApi';
import type { PaginatedParams } from '../models/common';
import type { UpdateCustomerRequest } from '../models/customer';

const CUSTOMERS_KEY = ['customers'];

export const useCustomers = (params: PaginatedParams) => {
  return useQuery({
    queryKey: [...CUSTOMERS_KEY, params],
    queryFn: () => customerApi.list(params),
    staleTime: 30_000,
  });
};

export const useCreateCustomer = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: customerApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CUSTOMERS_KEY }),
  });
};

export const useUpdateCustomer = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateCustomerRequest }) =>
      customerApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CUSTOMERS_KEY }),
  });
};

export const useDeleteCustomer = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: customerApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CUSTOMERS_KEY }),
  });
};
