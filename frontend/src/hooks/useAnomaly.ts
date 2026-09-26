import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acknowledgeAlarm,
  getAlarms,
  getCaptureMode,
  getCaptureScores,
  getDetectorScores,
  getSensitivity,
  setSensitivity,
} from "@/api/anomaly";
import type { SensitivityProfile } from "@/types/anomaly";

/**
 * Reading Phase 2 from the screens.
 *
 * None of these retries, and none of them falls back to a cheerful default.
 * A failed request leaves a machine in exactly the state "we do not know"
 * describes, and the panels above have an honest way to say that. The one
 * thing they must never do is come back looking like a clean bill of health,
 * which is what an empty array or a zero would be read as.
 */

export function useCaptureScores(uploadId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["anomaly-scores", uploadId],
    queryFn: () => getCaptureScores(uploadId as string),
    enabled: Boolean(uploadId),
    staleTime: 60_000,
    retry: false,
  });

  return {
    capture: query.data,
    isLoading: Boolean(uploadId) && query.isLoading,
    isError: query.isError,
  };
}

export function useDetectorScores(uploadId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["anomaly-detectors", uploadId],
    queryFn: () => getDetectorScores(uploadId as string),
    enabled: Boolean(uploadId),
    staleTime: 60_000,
    retry: false,
  });

  return {
    detectors: query.data,
    isLoading: Boolean(uploadId) && query.isLoading,
    isError: query.isError,
  };
}

/**
 * What is ringing on a machine, and what is being held back.
 *
 * Refetched on an interval because an alarm is the one thing here that a
 * person is waiting on, and a stale screen that says "all quiet" is worse
 * than no screen.
 */
export function useAlarms(sensorId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["anomaly-alarms", sensorId],
    queryFn: () => getAlarms(sensorId as string),
    enabled: Boolean(sensorId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  });

  return {
    summary: query.data,
    isLoading: Boolean(sensorId) && query.isLoading,
    isError: query.isError,
  };
}

/**
 * Acknowledging does not silence anything.
 *
 * The server returns the summary with the alarm still in it, and that is
 * what lands in the cache — so the screen keeps showing it, now marked as
 * seen. Anything that removed the row here would make "seen" and "resolved"
 * the same word.
 */
export function useAcknowledgeAlarm(sensorId: string | null | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { channel: number; featureCode: string; note?: string }) =>
      acknowledgeAlarm({ sensorId: sensorId as string, ...payload }),
    onSuccess: (summary) => {
      queryClient.setQueryData(["anomaly-alarms", sensorId], summary);
    },
  });
}

export function useSensitivity(equipmentId: string | null | undefined) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["anomaly-sensitivity", equipmentId],
    queryFn: () => getSensitivity(equipmentId as string),
    enabled: Boolean(equipmentId),
    staleTime: 60_000,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (input: {
      profile: SensitivityProfile;
      overrides?: Record<string, number>;
    }) => setSensitivity(equipmentId as string, input.profile, input.overrides),
    onSuccess: (settings) => {
      queryClient.setQueryData(["anomaly-sensitivity", equipmentId], settings);
      // Changing sensitivity changes what counts as an alarm, so anything
      // showing the old verdict is now wrong.
      queryClient.invalidateQueries({ queryKey: ["anomaly-alarms"] });
    },
  });

  return {
    sensitivity: query.data,
    isLoading: Boolean(equipmentId) && query.isLoading,
    isError: query.isError,
    save: mutation.mutate,
    isSaving: mutation.isPending,
  };
}

/**
 * The operating mode one capture was taken in.
 *
 * `null` means no verdict was ever recorded, which the API already keeps
 * apart from a verdict of "unknown" — the first is a capture nothing looked
 * at, the second is the engine declining to guess what load the machine was
 * under. A screen that showed them the same way would be reporting a
 * judgement nobody made.
 */
export function useCaptureMode(uploadId: string | null | undefined) {
  const query = useQuery({
    queryKey: ["capture-mode", uploadId],
    queryFn: () => getCaptureMode(uploadId as string),
    enabled: Boolean(uploadId),
    staleTime: 60_000,
    retry: false,
  });

  return {
    mode: query.data ?? null,
    isLoading: Boolean(uploadId) && query.isLoading,
    isError: query.isError,
  };
}
