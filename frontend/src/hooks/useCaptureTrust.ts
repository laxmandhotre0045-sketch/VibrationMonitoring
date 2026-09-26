import { useQuery } from "@tanstack/react-query";
import { getUploadFeatures } from "@/api/measurements";
import type { TrustLevel } from "@/types/features";

export interface CaptureTrust {
  trustLevel: TrustLevel | null;
  failedChecks: string[];
  notAssessedChecks: string[];
  isLoading: boolean;
}

/**
 * The quality verdict for a whole capture.
 *
 * Fetched without a channel on purpose. The endpoint scopes its verdict to the
 * channel it is asked about, and the capture selector selects a capture, not a
 * channel — asking for channel 0 would report that channel's verdict as the
 * whole capture's and could call a capture trustworthy while another channel
 * was clipped.
 *
 * A failed request reports no verdict rather than an error: the badge already
 * has an honest way to say "nothing has assessed this", and a capture whose
 * quality could not be fetched is in exactly that position. It must never fall
 * back to looking like a pass.
 */
export function useCaptureTrust(uploadId: string | null | undefined): CaptureTrust {
  const query = useQuery({
    queryKey: ["upload-features", uploadId, "capture-trust"],
    queryFn: () => getUploadFeatures(uploadId as string),
    enabled: Boolean(uploadId),
    staleTime: 60_000,
    retry: false,
  });

  return {
    trustLevel: query.data?.trust_level ?? null,
    failedChecks: query.data?.failed_checks ?? [],
    notAssessedChecks: query.data?.not_assessed_checks ?? [],
    isLoading: Boolean(uploadId) && query.isLoading,
  };
}
