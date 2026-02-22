import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";
import type { ResourceAction } from "@/types";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.getHealth, refetchInterval: 30_000 });
}

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
}

export function useResources(providerId?: string) {
  return useQuery({
    queryKey: ["resources", providerId],
    queryFn: () => api.listResources(providerId),
    refetchInterval: 15_000,
  });
}

export function useResourceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: ResourceAction }) =>
      api.performAction(id, action),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["resources"] }),
  });
}

export function useSyncResources() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerId: string) => api.syncResources(providerId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["resources"] }),
  });
}
