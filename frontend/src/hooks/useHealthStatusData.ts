import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAllPlots } from "@/api/measurements";
import { computeHealthMetrics } from "@/lib/health-metrics";
import type { HealthStatusSnapshot } from "@/types/health-status";

interface UseHealthStatusDataOptions {
  uploadId: string;
  channel: number;
  samplingRateHz: number;
  enabled?: boolean;
}

export function useHealthStatusData({
  uploadId,
  channel,
  samplingRateHz,
  enabled = true,
}: UseHealthStatusDataOptions) {
  const query = useQuery({
    queryKey: ["health-status-plots", uploadId, channel],
    queryFn: () => getAllPlots(uploadId, channel),
    enabled: enabled && !!uploadId,
    retry: 1,
  });

  const snapshot = useMemo((): HealthStatusSnapshot | null => {
    if (!query.data) return null;
    const computed = computeHealthMetrics(query.data.plots, channel, samplingRateHz);
    return {
      channel,
      channelLabel: `CH-${channel + 1}`,
      ...computed,
    };
  }, [query.data, channel, samplingRateHz]);

  return {
    ...query,
    snapshot,
  };
}
