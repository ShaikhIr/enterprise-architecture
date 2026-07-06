import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { entityApi } from '../api/entityApi';
import type { PaginatedParams } from '../models/common';
import type { UpdateEntityRequest } from '../models/entity';

const ENTITIES_KEY = ['entities'];
const ENTITY_DROPDOWN_KEY = ['entities', 'dropdown'];

export const useEntities = (params: PaginatedParams) => {
  return useQuery({
    queryKey: [...ENTITIES_KEY, params],
    queryFn: () => entityApi.list(params),
    staleTime: 30_000,
  });
};

export const useEntityDropdown = () => {
  return useQuery({
    queryKey: ENTITY_DROPDOWN_KEY,
    queryFn: () => entityApi.dropdown(),
    staleTime: 60_000,
  });
};

export const useCreateEntity = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: entityApi.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ENTITIES_KEY }),
  });
};

export const useUpdateEntity = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateEntityRequest }) =>
      entityApi.update(id, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ENTITIES_KEY }),
  });
};
