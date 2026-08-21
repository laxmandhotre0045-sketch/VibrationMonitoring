import { useQuery } from "@tanstack/react-query";
import { getCasingOrbit } from "@/api/measurements";
import type { CasingOrbitResponse } from "@/types/orbit";

interface UseCasingOrbitOptions {
  uploadId: string;
  xChannel: number;
  yChannel: number;
  harmonic: number;
  bandwidthPercent: number;
  filterRevolutions?: number;
  displayRevolutions: number;
  includeUnfiltered: boolean;
  enabled?: boolean;
}

export interface CasingOrbitData {
  data: CasingOrbitResponse | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
  hasSignal: boolean;
}

/**
 * FFT -> band filter -> double integration -> IFFT runs server-side and is expensive,
 * so the query key carries every parameter that changes the result. Nothing recomputes
 * on hover or on unrelated UI state.
 */
export function useCasingOrbit({
  uploadId,
  xChannel,
  yChannel,
  harmonic,
  bandwidthPercent,
  filterRevolutions,
  displayRevolutions,
  includeUnfiltered,
  enabled = true,
}: UseCasingOrbitOptions): CasingOrbitData {
  const query = useQuery({
    queryKey: [
      "casing-orbit",
      uploadId,
      xChannel,
      yChannel,
      harmonic,
      bandwidthPercent,
      filterRevolutions ?? "auto",
      displayRevolutions,
      includeUnfiltered,
    ],
    queryFn: () =>
      getCasingOrbit({
        uploadId,
        xChannel,
        yChannel,
        harmonic,
        bandwidthPercent,
        displayRevolutions,
        includeUnfiltered,
        ...(filterRevolutions !== undefined ? { filterRevolutions } : {}),
      }),
    enabled: enabled && !!uploadId && xChannel !== yChannel,
    staleTime: 60_000,
    gcTime: 300_000,
    retry: 1,
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
    hasSignal: !!query.data && query.data.peak_displacement_um > 0,
  };
}
