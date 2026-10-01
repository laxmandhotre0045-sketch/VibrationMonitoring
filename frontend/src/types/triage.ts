/**
 * Phase 3 and Phase 4 as the screens see them — sections 15, 16 and 20.
 *
 * Written from the endpoints' recorded responses rather than from the
 * routers, because a field spelled one way in Python and another in
 * TypeScript compiles perfectly and renders blank.
 *
 * Nullable fields are nullable here too, and deliberately so. `score: number
 * | null` is the platform saying it could not work one out, and a type that
 * quietly promised a number would push a zero onto the screen where the
 * honest answer is "nobody has measured this". Every `| null` below is a
 * case the UI has to render as words.
 */

/** Section 15.2's priority bands, worst first. */
export type PriorityBand =
  | "immediate"
  | "high"
  | "medium"
  | "low"
  | "watch"
  | "suppressed"
  | "unknown";

/** How urgent a finding is, from `app.ai.recommendation`. */
export type Urgency =
  | "none"
  | "monitor"
  | "inspect_when_convenient"
  | "inspect_soon"
  | "plan_maintenance"
  | "immediate";

/** Which way a finding is moving. `unknown` means too few readings. */
export type TrendDirection = "rising" | "steady" | "falling" | "unknown";

/** Where a finding sits in the triage workflow (section 15.2's "Status"). */
export type TriageStatus =
  | "new"
  | "assigned"
  | "investigating"
  | "awaiting_shutdown"
  | "resolved"
  | "closed";

/** Section 16.1's eleven feedback options. */
export type FeedbackVerdict =
  | "correct_detection"
  | "false_alarm"
  | "wrong_fault_type"
  | "severity_too_high"
  | "severity_too_low"
  | "maintenance_confirmed"
  | "fault_not_found"
  | "sensor_issue"
  | "process_related"
  | "ignore_for_machine"
  | "new_fault_label";

/** One row of the priority queue. Section 15.2 lists ten required fields. */
export interface QueueItem {
  rank: number;
  /** Addresses every action a screen can take: feedback, assignment. */
  finding_id: string;
  machine_name: string | null;
  sensor_id: string;
  channel: number;
  fault_suspected: string;
  fault_key: string;
  family: string | null;
  severity: number;
  stage: string;
  confidence: number;
  recommended_action: string | null;
  urgency: Urgency;
  shutdown_advised: boolean;
  first_detected_at: string | null;
  days_since_detected: number | null;
  trend_direction: TrendDirection;
  assigned_analyst: string | null;
  status: TriageStatus;
  priority_score: number | null;
  priority_band: PriorityBand;
  priority_reason: string;
  /** Inputs the platform could not obtain. Shown, never silently defaulted. */
  unknowns: string[];
  latest_feedback: FeedbackVerdict | null;
  suppressed: boolean;
}

export interface QueueResponse {
  queue: QueueItem[];
  count: number;
  reason: string;
}

/** What a verdict means and what submitting it actually changes. */
export interface VerdictOption {
  value: FeedbackVerdict;
  label: string;
  /** What the platform changes today. */
  effect: string;
  /** What the row is kept for. */
  learns: string;
}

export interface VerdictsResponse {
  verdicts: VerdictOption[];
  count: number;
}

export interface FeedbackRequest {
  verdict: FeedbackVerdict;
  note?: string | null;
  corrected_fault_key?: string | null;
  corrected_fault_label?: string | null;
  corrected_severity?: number | null;
  retracts_id?: string | null;
  suppression_days?: number;
}

/** What this machine's feedback history says about this fault. */
export interface Standing {
  adjustment: number;
  confirmed: number;
  rejected: number;
  severity_shift: number;
  reason: string;
  notes: string[];
}

/**
 * The response to submitting feedback. It returns what changed rather than
 * an acknowledgement: an analyst who marks a false alarm and gets back
 * "recorded" has no reason to believe anything happened, and stops
 * bothering.
 */
export interface FeedbackResult {
  recorded: FeedbackVerdict;
  effect: string;
  learns: string;
  applied: string[];
  standing: Standing;
}

export interface AssignRequest {
  analyst: string | null;
  status?: TriageStatus | null;
}

export interface AssignResult {
  assigned_to: string | null;
  assigned_at: string | null;
  triage_status: TriageStatus;
}

export interface FeedbackSummary {
  total: number;
  by_verdict: Record<
    FeedbackVerdict,
    { count: number; label: string; effect: string; learns: string }
  >;
  corrections_awaiting_a_rule: Array<{
    fault_key: string;
    corrected_fault_key: string | null;
    corrected_fault_label: string | null;
    n: number;
  }>;
  most_rejected_rules: Array<{ fault_key: string; rejections: number }>;
  confirmed: number;
  rejected: number;
  reason: string;
}
