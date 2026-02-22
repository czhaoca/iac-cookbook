import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/api/client";
import type { ResourceAction, BudgetRuleCreate } from "@/types";

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

// Budget
export function useBudgetRules() {
  return useQuery({ queryKey: ["budget-rules"], queryFn: api.listBudgetRules });
}

export function useBudgetStatus() {
  return useQuery({
    queryKey: ["budget-status"],
    queryFn: api.getBudgetStatus,
    refetchInterval: 60_000,
  });
}

export function useSpending(providerId?: string) {
  return useQuery({
    queryKey: ["spending", providerId],
    queryFn: () => api.listSpending(providerId),
  });
}

export function useCreateBudgetRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BudgetRuleCreate) => api.createBudgetRule(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["budget-rules"] });
      qc.invalidateQueries({ queryKey: ["budget-status"] });
    },
  });
}

export function useDeleteBudgetRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteBudgetRule(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["budget-rules"] });
      qc.invalidateQueries({ queryKey: ["budget-status"] });
    },
  });
}

export function useEnforceBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.enforceBudget(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget-status"] }),
  });
}

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
}

export function useProviderStatus() {
  return useQuery({
    queryKey: ["provider-status"],
    queryFn: api.getProviderStatus,
    refetchInterval: 30_000,
  });
}

export function useErrors(source?: string) {
  return useQuery({
    queryKey: ["errors", source],
    queryFn: () => api.getErrors(source, 100),
    refetchInterval: 30_000,
  });
}
