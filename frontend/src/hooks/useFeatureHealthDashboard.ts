import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { compareUploadFeatures, getUploadFeatures } from "@/api/measurements";
import {
  enrichFeatureCompareItems,
  enrichFeatureStatusItems,
} from "@/lib/feature-display";
import { deriveHealthState, summarizeFeatureItems } from "@/lib/health-feature-fallback";
import type { Baseline } from "@/types/baseline";
import type {
  ChannelHealthOverviewData,
  FeatureCompareItem,
  FeatureStatusItem,
  FeatureSummaryCounts,
} from "@/types/features";

interface UseFeatureHealthDashboardOptions {
  sensorId: string;
  uploadId: string;
  channel: number;
  primaryBaseline: Baseline | null | undefined;
  baselineList: Baseline[] | undefined;
  enabled?: boolean;
}

export function useFeatureHealthDashboard({
  sensorId,
  uploadId,
  channel,
  primaryBaseline,
  baselineList,
  enabled = true,
}: UseFeatureHealthDashboardOptions) {
  const [compareBaselineId, setCompareBaselineId] = useState("");
  const compareContextRef = useRef({ uploadId: "", channel: 0 });

  const isEnabled = enabled && !!sensorId && !!uploadId;

  useEffect(() => {
    const uploadChanged = compareContextRef.current.uploadId !== uploadId;
    compareContextRef.current = { uploadId, channel };

    if (!uploadChanged && compareBaselineId) return;

    if (primaryBaseline?.id) {
      setCompareBaselineId(primaryBaseline.id);
      return;
    }
    if (baselineList?.[0]?.id) {
      setCompareBaselineId(baselineList[0].id);
      return;
    }
    setCompareBaselineId("");
  }, [uploadId, channel, primaryBaseline?.id, baselineList, compareBaselineId]);

  const selectedBaseline =
    baselineList?.find((b) => b.id === compareBaselineId) ?? primaryBaseline ?? null;

  const featuresQuery = useQuery({
    queryKey: ["upload-features", uploadId, channel],
    queryFn: () => getUploadFeatures(uploadId, channel),
    enabled: isEnabled,
    retry: 1,
  });

  const compareQuery = useQuery({
    queryKey: ["upload-features-compare", uploadId, channel, compareBaselineId],
    queryFn: () => compareUploadFeatures(uploadId, compareBaselineId, channel),
    enabled: isEnabled && !!compareBaselineId,
    retry: 1,
  });

  const featureItems = useMemo((): FeatureStatusItem[] => {
    if (!featuresQuery.data?.items) return [];
    return enrichFeatureStatusItems(featuresQuery.data.items);
  }, [featuresQuery.data]);

  const compareItems = useMemo((): FeatureCompareItem[] => {
    if (!compareQuery.data?.items) return [];
    return enrichFeatureCompareItems(compareQuery.data.items);
  }, [compareQuery.data]);

  const summary = useMemo((): FeatureSummaryCounts => {
    if (featuresQuery.data?.summary && featuresQuery.data.summary.total > 0) {
      return featuresQuery.data.summary;
    }
    return summarizeFeatureItems(featureItems);
  }, [featuresQuery.data, featureItems]);

  const channelOverview = useMemo((): ChannelHealthOverviewData | null => {
    const baselineName = selectedBaseline?.name ?? primaryBaseline?.name ?? null;
    const baselineId = selectedBaseline?.id ?? primaryBaseline?.id ?? null;

    if (featuresQuery.data?.channel_overview) {
      return {
        ...featuresQuery.data.channel_overview,
        baseline_name: featuresQuery.data.channel_overview.baseline_name ?? baselineName,
        baseline_id: featuresQuery.data.channel_overview.baseline_id ?? baselineId,
      };
    }
    if (compareQuery.data?.channel_overview) {
      return {
        ...compareQuery.data.channel_overview,
        baseline_name: compareQuery.data.channel_overview.baseline_name ?? baselineName,
        baseline_id: compareQuery.data.channel_overview.baseline_id ?? baselineId,
      };
    }
    if (!featuresQuery.isSuccess) return null;
    return {
      health_state: deriveHealthState(summary),
      feature_count: summary.total,
      computed_at: null,
      baseline_name: baselineName,
      baseline_id: baselineId,
    };
  }, [
    featuresQuery.data,
    featuresQuery.isSuccess,
    compareQuery.data,
    summary,
    selectedBaseline,
    primaryBaseline,
  ]);

  const compareIsLoading = !!compareBaselineId && compareQuery.isLoading;

  const compareHasApiError =
    !!compareBaselineId && compareQuery.isError && !compareQuery.data?.items?.length;

  const isLoading = isEnabled && featuresQuery.isLoading;

  const hasFeatureData =
    featuresQuery.isSuccess &&
    featureItems.some((item) => item.value !== null && item.value !== undefined);

  const hasFeatureTable =
    featuresQuery.isSuccess && featureItems.length > 0;

  return {
    featuresQuery,
    compareQuery,
    featureItems,
    compareItems,
    summary,
    channelOverview,
    compareBaselineId,
    setCompareBaselineId,
    selectedBaseline,
    baselineOptions: baselineList ?? [],
    isLoading,
    hasFeatureData,
    hasFeatureTable,
    usesApiFeatures: !!featuresQuery.data?.items?.length,
    usesApiCompare: !!compareQuery.data?.items?.length,
    compareIsLoading,
    compareHasApiError,
  };
}
