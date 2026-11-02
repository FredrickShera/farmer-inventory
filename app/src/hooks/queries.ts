import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { PAGE_SIZE } from '../config';
import type { Farmer, InventoryFilters, InventoryInput, InventoryItem, Location, Page, ProduceType } from '../api/types';

export const useLocations = () => {
  const { client } = useAuth();
  return useQuery({ queryKey: ['locations'], staleTime: 24 * 3600_000, queryFn: () => client.request<Location[]>('/locations', { auth: false }) });
};

export const useProduceTypes = () => {
  const { client } = useAuth();
  return useQuery({ queryKey: ['produce-types'], staleTime: 3600_000, queryFn: () => client.request<ProduceType[]>('/produce-types') });
};

export const useProfile = () => {
  const { client } = useAuth();
  return useQuery({ queryKey: ['me'], queryFn: () => client.request<Farmer>('/farmers/me') });
};

export const useInventory = (filters: InventoryFilters) => {
  const { client } = useAuth();
  return useInfiniteQuery({
    queryKey: ['inventory', filters],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => client.request<Page<InventoryItem>>('/inventory', { query: { ...filters, page: pageParam, page_size: PAGE_SIZE } }),
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
  });
};

export const useSaveItem = () => {
  const { client } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: Partial<InventoryInput> }) =>
      id ? client.request<InventoryItem>(`/inventory/${id}`, { method: 'PATCH', body: input })
         : client.request<InventoryItem>('/inventory', { method: 'POST', body: input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory'] }),
  });
};

export const useDeleteItem = () => {
  const { client } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.request<void>(`/inventory/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory'] }),
  });
};
