import { useQuery } from "@tanstack/react-query";
import { getCaptureHistory } from "@/api/dashboard";

/**
 * Capture history for the freshness and 7/30-day cards.
 *
 * Refetched every 30 s rather than the 60 s the fleet summary uses: the whole
 * point of the freshness card is to show that the feed is alive, and a card
 * that can be a minute out of date is a poor witness to that.
 */
export function useCaptureHistory(sensorId?: string) {
  return useQuery({
    queryKey: ["capture-history", sensorId ?? "all"],
    queryFn: () => getCaptureHistory(sensorId),
    retry: 1,
    refetchInterval: 30_000,
  });
}
