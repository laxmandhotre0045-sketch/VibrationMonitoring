import api from "./client";
import type {
  ThresholdRule,
  ThresholdRuleBulkItem,
  ThresholdRuleCreate,
  ThresholdRuleList,
  ThresholdRuleUpdate,
} from "@/types/thresholds";

const BASE = "/api/v1/thresholds";

export async function listThresholdRules(params?: {
  machineType?: string;
  channel?: number;
  includeInactive?: boolean;
}): Promise<ThresholdRuleList> {
  const res = await api.get(`${BASE}/rules`, {
    params: {
      machine_type: params?.machineType,
      channel: params?.channel,
      include_inactive: params?.includeInactive,
    },
  });
  return res.data;
}

export async function updateThresholdRule(
  ruleId: string,
  patch: ThresholdRuleUpdate
): Promise<ThresholdRule> {
  const res = await api.put(`${BASE}/rules/${ruleId}`, patch);
  return res.data;
}

/** Save a whole editor screen. Rejected as a unit if any row is invalid. */
export async function bulkUpdateThresholdRules(
  items: ThresholdRuleBulkItem[]
): Promise<ThresholdRuleList> {
  const res = await api.put(`${BASE}/rules`, { items });
  return res.data;
}

/** Create a channel-specific override of a feature's global rule. */
export async function createThresholdRule(
  payload: ThresholdRuleCreate
): Promise<ThresholdRule> {
  const res = await api.post(`${BASE}/rules`, payload);
  return res.data;
}

/** Restore one rule's factory limits. */
export async function resetThresholdRule(ruleId: string): Promise<ThresholdRule> {
  const res = await api.post(`${BASE}/rules/${ruleId}/reset`);
  return res.data;
}

/** Drop a channel override so the channel follows the global rule again. */
export async function deleteThresholdRule(ruleId: string): Promise<void> {
  await api.delete(`${BASE}/rules/${ruleId}`);
}
