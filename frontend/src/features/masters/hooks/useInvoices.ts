import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoiceApi } from '../api/invoiceApi';
import type { CreateInvoiceRequest, PaymentUpdateRequest } from '../models/invoice';
import type { PaginatedParams } from '../models/common';

const INVOICES_KEY = ['invoices'];

export const useInvoices = (params: PaginatedParams, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: [...INVOICES_KEY, params],
    queryFn: () => invoiceApi.list(params),
    staleTime: 30_000,
    enabled: options?.enabled ?? true,
  });
};

export const useCreateInvoice = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateInvoiceRequest) => invoiceApi.create(request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVOICES_KEY }),
  });
};

export const useUpdatePayment = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: PaymentUpdateRequest }) =>
      invoiceApi.updatePayment(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVOICES_KEY }),
  });
};

export const useMarkSettled = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => invoiceApi.markSettled(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INVOICES_KEY }),
  });
};

export const useCheckEligibility = (id: string, enabled: boolean) => {
  return useQuery({
    queryKey: [...INVOICES_KEY, id, 'eligibility'],
    queryFn: () => invoiceApi.checkEligibility(id),
    enabled,
    staleTime: 30_000,
  });
};
