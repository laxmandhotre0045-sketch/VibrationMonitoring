import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  assignFinding,
  getFeedbackSummary,
  getQueue,
  getVerdicts,
  submitFeedback,
} from "@/api/triage";
import type { AssignRequest, FeedbackRequest } from "@/types/triage";

/**
 * Reading and answering the priority queue.
 *
 * None of these retries, and none falls back to a cheerful default. A failed
 * request leaves the screen in the state "we do not know" describes, and the
 * panels have an honest way to say that. What they must never do is come
 * back looking like an empty queue, because an empty queue reads as "nothing
 * needs attention" — which on this gateway is exactly the wrong conclusion.
 */

export function useTriageQueue(limit = 50, includeSuppressed = false) {
  const query = useQuery({
    queryKey: ["triage-queue", limit, includeSuppressed],
    queryFn: () => getQueue(limit, includeSuppressed),
    staleTime: 30_000,
    retry: false,
  });

  return {
    /** Undefined while loading or on error — never an invented empty list. */
    data: query.data,
    items: query.data?.queue ?? [],
    reason: query.data?.reason ?? "",
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}

/**
 * The eleven verdicts and what each changes.
 *
 * Cached for an hour: it is reference data that changes with a deploy, and
 * re-fetching it on every render would be noise. It is still fetched rather
 * than hard-coded, because the effect text is the platform's own account of
 * what it does with the feedback.
 */
export function useVerdicts() {
  const query = useQuery({
    queryKey: ["triage-verdicts"],
    queryFn: getVerdicts,
    staleTime: 60 * 60_000,
    retry: false,
  });

  return {
    verdicts: query.data?.verdicts ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function useFeedbackSummary() {
  const query = useQuery({
    queryKey: ["triage-feedback-summary"],
    queryFn: getFeedbackSummary,
    staleTime: 60_000,
    retry: false,
  });

  return {
    summary: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

/**
 * Submitting an analyst's verdict.
 *
 * Invalidates the queue on success, because the whole point is that the
 * feedback moves the ranking. A queue that still shows the old order after
 * a correction teaches the analyst that nothing happened.
 */
export function useSubmitFeedback() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      findingId,
      body,
    }: {
      findingId: string;
      body: FeedbackRequest;
    }) => submitFeedback(findingId, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["triage-queue"] });
      client.invalidateQueries({ queryKey: ["triage-feedback-summary"] });
    },
  });
}

export function useAssignFinding() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      findingId,
      body,
    }: {
      findingId: string;
      body: AssignRequest;
    }) => assignFinding(findingId, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["triage-queue"] });
    },
  });
}
