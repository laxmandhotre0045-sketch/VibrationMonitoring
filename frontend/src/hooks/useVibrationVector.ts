import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getVibrationVector } from "@/api/measurements";
import { buildPolarVectorModel, type PolarVectorModel } from "@/lib/polar-vector-transform";
import type { VibrationVectorResponse } from "@/types/vector";

interface UseVibrationVectorOptions {
  uploadId: string;
  channel: number;
  targetHz?: number;
  blockSize?: number;
  enabled?: boolean;
}

export interface VibrationVectorData {
  data: VibrationVectorResponse | undefined;
  model: PolarVectorModel | null;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
  hasBlocks: boolean;
}

export function useVibrationVector({
  uploadId,
  channel,
  targetHz,
  blockSize,
  enabled = true,
}: UseVibrationVectorOptions): VibrationVectorData {
  const query = useQuery({
    queryKey: ["vibration-vector", uploadId, channel, targetHz ?? null, blockSize ?? null],
    queryFn: () =>
      getVibrationVector({
        uploadId,
        channel,
        ...(targetHz !== undefined ? { targetHz } : {}),
        ...(blockSize !== undefined ? { blockSize } : {}),
      }),
    enabled: enabled && !!uploadId,
    staleTime: 60_000,
    gcTime: 300_000,
    retry: 1,
  });

  // Transform once per response so the chart keeps a stable reference.
  const model = useMemo(
    () => (query.data ? buildPolarVectorModel(query.data) : null),
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
    hasBlocks: !!model && model.points.length > 0,
  };
}
