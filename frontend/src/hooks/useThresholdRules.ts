import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkUpdateThresholdRules,
  createThresholdRule,
  deleteThresholdRule,
  listThresholdRules,
  resetThresholdRule,
  updateThresholdRule,
} from "@/api/thresholds";
import { resolveVibrationFeatureKey } from "@/lib/vibration-features";
import type {
  ResolvedThresholdRule,
  ThresholdRule,
  ThresholdRuleBulkItem,
  ThresholdRuleUpdate,
} from "@/types/thresholds";

export const THRESHOLD_RULES_KEY = ["threshold-rules"] as const;

/**
 * The threshold rules, plus the resolution the editor needs.
 *
 * Storage keeps one row per scope: a global row per feature, and a row per
 * channel that overrides it. The Settings table is a channel x parameter grid,
 * so every cell has to be resolved — override if the channel has one, otherwise
 * the global row it inherits. `resolveFor` does that lookup; `isOverridden`
 * tells the UI whether a cell is showing its own value or a borrowed one.
 */
export function useThresholdRules(options?: { enabled?: boolean }) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: THRESHOLD_RULES_KEY,
    queryFn: () => listThresholdRules(),
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  });

  const rules = useMemo(() => query.data?.items ?? [], [query.data]);

  const globalByCode = useMemo(() => {
    const map = new Map<string, ThresholdRule>();
    for (const rule of rules) {
      if (rule.channel === null && rule.machine_type === null) {
        map.set(rule.feature_code, rule);
      }
    }
    return map;
  }, [rules]);

  const overrideByChannelCode = useMemo(() => {
    const map = new Map<string, ThresholdRule>();
    for (const rule of rules) {
      if (rule.channel !== null) {
        map.set(`${rule.channel}:${rule.feature_code}`, rule);
      }
    }
    return map;
  }, [rules]);

  /** Feature codes in the order the backend defines them. */
  const featureCodes = useMemo(
    () => Array.from(globalByCode.keys()),
    [globalByCode]
  );

  const resolveFor = useCallback(
    (channel: number | null, featureCode: string): ResolvedThresholdRule | null => {
      const globalRule = globalByCode.get(featureCode) ?? null;
      const override =
        channel === null
          ? null
          : overrideByChannelCode.get(`${channel}:${featureCode}`) ?? null;
      const effective = override ?? globalRule;
      if (!effective) return null;

      return {
        featureKey: resolveVibrationFeatureKey(featureCode),
        featureCode,
        rule: effective,
        override,
        global: globalRule,
        isOverridden: override !== null,
      };
    },
    [globalByCode, overrideByChannelCode]
  );

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: THRESHOLD_RULES_KEY });
    // Limits are shown next to live readings on the health screens, so a rule
    // change has to reach those too rather than waiting for their own staleTime.
    void queryClient.invalidateQueries({ queryKey: ["upload-factor-trends"] });
    void queryClient.invalidateQueries({ queryKey: ["upload-features"] });
  }, [queryClient]);

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ThresholdRuleUpdate }) =>
      updateThresholdRule(id, patch),
    onSuccess: invalidate,
  });

  const bulkUpdate = useMutation({
    mutationFn: (items: ThresholdRuleBulkItem[]) => bulkUpdateThresholdRules(items),
    onSuccess: invalidate,
  });

  const create = useMutation({
    mutationFn: createThresholdRule,
    onSuccess: invalidate,
  });

  const reset = useMutation({
    mutationFn: resetThresholdRule,
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: deleteThresholdRule,
    onSuccess: invalidate,
  });

  return {
    query,
    rules,
    ruleTypes: query.data?.rule_types ?? {},
    overriddenChannels: query.data?.overridden_channels ?? [],
    featureCodes,
    globalByCode,
    resolveFor,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    update,
    bulkUpdate,
    create,
    reset,
    remove,
    isSaving:
      update.isPending ||
      bulkUpdate.isPending ||
      create.isPending ||
      reset.isPending ||
      remove.isPending,
  };
}
