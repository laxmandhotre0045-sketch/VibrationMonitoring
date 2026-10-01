import { useQuery } from "@tanstack/react-query";

import { getFleet, getOperatorView, getReliability } from "@/api/dashboards";

/**
 * Reading section 19's dashboards.
 *
 * None retries and none falls back to an empty success. A failed request
 * leaves the screen in the state "we do not know" describes, which the
 * panels say out loud — what they must never do is render as a plant with
 * nothing wrong.
 */

export function useOperatorView(plantName?: string) {
  const query = useQuery({
    queryKey: ["operator-view", plantName ?? null],
    queryFn: () => getOperatorView(plantName),
    staleTime: 30_000,
    retry: false,
  });
  return {
    data: query.data,
    machines: query.data?.machines ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function useFleet(plantName?: string) {
  const query = useQuery({
    queryKey: ["fleet-view", plantName ?? null],
    queryFn: () => getFleet(plantName),
    staleTime: 60_000,
    retry: false,
  });
  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function useReliability(sensorId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["reliability", sensorId],
    queryFn: () => getReliability(sensorId as string),
    enabled: Boolean(sensorId),
    staleTime: 60_000,
    retry: false,
  });
  return {
    reliability: query.data,
    isLoading: Boolean(sensorId) && query.isLoading,
    isError: query.isError,
  };
}
