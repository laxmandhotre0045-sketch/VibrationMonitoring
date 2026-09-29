import api from "./client";
import type {
  AssignRequest,
  AssignResult,
  FeedbackRequest,
  FeedbackResult,
  FeedbackSummary,
  QueueResponse,
  VerdictsResponse,
} from "@/types/triage";

/**
 * Phase 4: the priority queue and the analyst feedback loop.
 *
 * Nothing here invents a default. The queue can legitimately come back
 * empty, and on this gateway it does — no capture can yet resolve the
 * bearing frequencies, so no fault rule fires. The endpoint says that in
 * `reason` and this hands it through, because an empty list rendered as
 * "all clear" is the one failure the whole platform is built to avoid.
 */

/** The plant's priority queue, worst first. Recomputed server-side. */
export async function getQueue(
  limit = 50,
  includeSuppressed = false,
): Promise<QueueResponse> {
  const res = await api.get("/api/v1/triage/queue", {
    params: { limit, include_suppressed: includeSuppressed },
  });
  return res.data;
}

/**
 * The eleven things an analyst can say, and what each one changes.
 *
 * Fetched rather than hard-coded in the UI. The effect text is the
 * platform's own account of what it does with the feedback, and a copy
 * kept in the frontend would drift from it silently — which matters here
 * more than usual, because the promise that feedback is used is the only
 * reason anyone gives any.
 */
export async function getVerdicts(): Promise<VerdictsResponse> {
  const res = await api.get("/api/v1/triage/verdicts");
  return res.data;
}

/** Record one analyst report. Returns what it changed, not an ack. */
export async function submitFeedback(
  findingId: string,
  body: FeedbackRequest,
): Promise<FeedbackResult> {
  const res = await api.post(
    `/api/v1/triage/findings/${findingId}/feedback`,
    body,
  );
  return res.data;
}

/** Section 15.2's "Assigned analyst" and "Status". */
export async function assignFinding(
  findingId: string,
  body: AssignRequest,
): Promise<AssignResult> {
  const res = await api.post(
    `/api/v1/triage/findings/${findingId}/assign`,
    body,
  );
  return res.data;
}

/** What the loop has collected and what it is doing with it (16.2). */
export async function getFeedbackSummary(): Promise<FeedbackSummary> {
  const res = await api.get("/api/v1/triage/feedback/summary");
  return res.data;
}
