/**
 * The diagnosis endpoints as the screens see them — Phase 3.
 *
 * Same rule as `triage.ts`: every `| null` is a case the platform could not
 * work out, and the screen has to say so in words rather than render a zero.
 * `zone: null` on an ISO grade does not mean Zone A; `score: null` on a
 * health reading does not mean 100.
 */

/** One observation about the signal, with the numbers behind it. */
export interface Symptom {
  key: string;
  name: string;
  /** Plain sentences an analyst can check against the spectrum. */
  evidence: string[];
  detail: Record<string, unknown>;
}

export interface ChannelSymptoms {
  channel: number;
  symptoms: Symptom[];
  /** False when no shaft speed was established for the capture. */
  shaft_usable: boolean;
  checks_run: number;
  /** Below five when the order-based checks could not run. */
  checks_possible: number;
  created_at: string;
}

export interface SymptomsResponse {
  sensor_id: string;
  upload_id: string | null;
  channels: ChannelSymptoms[];
  observations: number;
  reason: string;
}

/** One piece of evidence a fault rule fired on. */
export interface Evidence {
  order: number | null;
  frequency_hz: number | null;
  amplitude: number | null;
  statement: string;
}

/** Whether the spectrum could separate the orders a diagnosis needs. */
export interface Resolution {
  usable: boolean;
  bin_hz: number | null;
  record_seconds: number | null;
  unresolved: Array<{
    defect: string;
    against: string;
    gap_hz: number;
    bins_apart: number;
    statement: string;
  }>;
  resolved: string[];
  needed_seconds: number | null;
  reason: string;
}

/** Which plot proves a fault, and why that plot (VIK-059). */
export interface PlotEvidence {
  plot_type: string;
  rank: number;
  what_to_look_for: string;
  why_this_plot: string;
}

export interface Finding {
  channel: number;
  fault_key: string;
  fault_name: string;
  family: string | null;
  score: number;
  confidence: number;
  stage: string;
  severity: number;
  mechanism: string | null;
  evidence: Evidence[];
  contradicting_evidence: Evidence[];
  confirming_checks: string[];
  resolution: Resolution | null;
  context_completeness: { available: string[]; missing: string[] } | null;
  symptoms: Symptom[];
  score_history: number[];
  direction: string;
  direction_reason: string | null;
  urgency: string;
  proposed_urgency: string | null;
  urgency_capped: boolean;
  urgency_reason: string | null;
  recommended_action: string | null;
  shutdown_advised: boolean;
  first_detected_at: string;
  last_seen_at: string;
  times_seen: number;
  peak_stage: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  analyst_verdict: string | null;
  plots: PlotEvidence[];
}

export interface FindingsResponse {
  sensor_id: string;
  findings: Finding[];
  /**
   * Travels beside an empty list on purpose. "No fault found" and "the
   * instrument could not have seen one" read identically otherwise.
   */
  resolution: Resolution | null;
  count: number;
  reason: string;
}

/** One input's effect on the health score, and the reason it had it. */
export interface HealthContribution {
  key: string;
  name: string;
  penalty: number;
  points_off: number;
  points_alone: number;
  reason: string;
  detail: Record<string, unknown>;
}

export interface HealthResponse {
  /** Null where nothing could be scored. Not the same as 100. */
  score: number | null;
  band: string;
  /** The most the score was allowed to reach, given how well it can be seen. */
  ceiling: number;
  data_quality: string | null;
  usable: boolean;
  criticality: string | null;
  priority: number | null;
  contributions: HealthContribution[];
  unknowns: string[];
  reason: string;
  sensor_id: string;
  last_upload_at: string | null;
  open_findings: number;
  machine_name: string | null;
}

export interface IsoCandidate {
  zone: string;
  zone_meaning: string;
  action: string;
  urgency: string;
  machine_group: number;
  group_name: string;
  foundation: string;
  boundaries_mm_s: Record<string, number>;
  margin_to_next_mm_s: number | null;
  next_zone: string | null;
}

export interface IsoResponse {
  usable: boolean;
  /** Null when the applicable tables disagree, or nothing could be graded. */
  zone: string | null;
  zone_range: [string, string] | null;
  worst_zone: string | null;
  velocity_rms_mm_s: number | null;
  band_hz: [number, number] | null;
  determined: boolean;
  candidates: IsoCandidate[];
  /** What would narrow the tables to one. */
  missing: string[];
  reason: string;
  sensor_id: string;
  channel: number;
  upload_id: string;
  machine_name: string | null;
}
