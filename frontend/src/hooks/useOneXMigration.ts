import { useQuery } from "@tanstack/react-query";
import { getOneXMigration } from "@/api/measurements";
import type { OneXMigrationResponse } from "@/types/migration";

interface UseOneXMigrationOptions {
  sensorId: string;
  xChannel: number;
  yChannel: number;
  count: number;
  mode: string;
  enabled?: boolean;
}

export interface OneXMigrationData {
  data: OneXMigrationResponse | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
  /** Migration needs at least two valid captures to mean anything. */
  hasMigration: boolean;
}

/**
 * One FFT per channel per capture runs server-side, so the query key carries every
 * parameter that changes the result and nothing recomputes on hover or unrelated state.
 */
export function useOneXMigration({
  sensorId,
  xChannel,
  yChannel,
  count,
  mode,
  enabled = true,
}: UseOneXMigrationOptions): OneXMigrationData {
  const query = useQuery({
    queryKey: ["one-x-migration", sensorId, xChannel, yChannel, count, mode],
    queryFn: () => getOneXMigration({ sensorId, xChannel, yChannel, count, mode }),
    enabled: enabled && !!sensorId && xChannel !== yChannel,
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
    hasMigration: (query.data?.summary.valid_count ?? 0) >= 2,
  };
}
