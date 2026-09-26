import { useQuery } from "@tanstack/react-query";
import { getBaselineHealth } from "@/api/baselines";

/**
 * How much the learned baseline in force for this sensor is worth.
 *
 * Not retried and never throws to the caller: the banner already has an honest
 * way to say "no verdict", and a health check that failed leaves the baseline
 * in exactly that position. It must not fall back to looking sound.
 */
export function useBaselineHealth(sensorId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["baseline-health", sensorId],
    queryFn: () => getBaselineHealth(sensorId as string),
    enabled: Boolean(sensorId),
    staleTime: 60_000,
    retry: false,
  });

  return {
    health: query.data,
    isLoading: Boolean(sensorId) && query.isLoading,
    isError: query.isError,
  };
}
