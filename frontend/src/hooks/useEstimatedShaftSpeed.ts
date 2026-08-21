import { useQuery } from "@tanstack/react-query";
import { getEstimatedShaftHz } from "@/api/measurements";

interface UseEstimatedShaftSpeedOptions {
  uploadId: string | null;
  channel: number;
  enabled?: boolean;
}

export interface EstimatedShaftSpeed {
  /** Estimated shaft frequency in Hz, or null when the capture has no usable estimate. */
  hz: number | null;
  /** Same value expressed as RPM (hz * 60). Always label this as estimated. */
  rpm: number | null;
  isLoading: boolean;
}

/**
 * Shaft speed for a single capture — the selected trace only, never all N.
 *
 * The value is derived from the stored FFT (largest bin between 5 and 120 Hz), so it is
 * an estimate. Failures resolve to null rather than surfacing an error: the field is
 * simply omitted when it is not available.
 */
export function useEstimatedShaftSpeed({
  uploadId,
  channel,
  enabled = true,
}: UseEstimatedShaftSpeedOptions): EstimatedShaftSpeed {
  const query = useQuery({
    queryKey: ["estimated-shaft-hz", uploadId, channel],
    queryFn: () => getEstimatedShaftHz(uploadId!, channel),
    enabled: enabled && !!uploadId,
    retry: false,
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
  });

  const hz = query.data ?? null;
  return {
    hz,
    rpm: hz != null ? hz * 60 : null,
    isLoading: query.isLoading,
  };
}
