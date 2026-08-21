import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getWaterfall } from "@/api/measurements";
import { buildWaterfallModel, type WaterfallModel } from "@/lib/waterfall-adapter";
import type { WaterfallMode, WaterfallResponse, WaterfallSpectrum } from "@/types/waterfall";

interface UseWaterfallDataOptions {
  sensorId: string;
  channel: number;
  count: number;
  mode: WaterfallMode;
  plotType: WaterfallSpectrum;
  /** Only used by mode "random" — keeps one selection stable until the user re-rolls. */
  seed?: number;
  maxPoints?: number;
  enabled?: boolean;
}

export interface WaterfallData {
  data: WaterfallResponse | undefined;
  model: WaterfallModel | null;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
  hasCaptures: boolean;
}

export function useWaterfallData({
  sensorId,
  channel,
  count,
  mode,
  plotType,
  seed,
  maxPoints,
  enabled = true,
}: UseWaterfallDataOptions): WaterfallData {
  const query = useQuery({
    queryKey: [
      "waterfall",
      sensorId,
      channel,
      count,
      mode,
      plotType,
      mode === "random" ? seed : null,
      maxPoints ?? null,
    ],
    queryFn: () =>
      getWaterfall({
        sensorId,
        channel,
        count,
        mode,
        plotType,
        maxPoints,
        ...(mode === "random" && seed !== undefined ? { seed } : {}),
      }),
    enabled: enabled && !!sensorId,
    staleTime: 60_000,
    gcTime: 300_000,
    retry: 1,
  });

  // Transform once per response, outside render, so the 3D scene keeps a stable reference.
  const model = useMemo(
    () => (query.data ? buildWaterfallModel(query.data) : null),
    [query.data]
  );

  return {
    data: query.data,
    model,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
    hasCaptures: !!model && model.lines.length > 0,
  };
}
