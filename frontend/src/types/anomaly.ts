/**
 * The Phase 2 payloads: how unusual each reading was, and what is ringing.
 *
 * One rule runs through every type here and it is the one the whole platform
 * rests on: **a score that could not be computed is `null`, never `0`.** A
 * reading nothing has ever been compared to is not a reading that looks
 * ordinary, and the moment those collapse into the same number an unmonitored
 * machine starts outranking a monitored healthy one on every list it appears
 * in — precisely because nobody is watching it.
 *
 * So `score` is `number | null` and `is_scored` carries the meaning. Read the
 * boolean; never test the number for truthiness.
 */

/** 0–20 normal, 21–40 slight, 41–60 watch, 61–75 abnormal, 76–90 high, 91–100 critical. */
export type AnomalyBand =
  | "normal"
  | "slight"
  | "watch"
  | "abnormal"
  | "high"
  | "critical";

export type SensitivityProfile =
  | "conservative"
  | "balanced"
  | "early_warning"
  | "expert";

/** Why a finding is past the line and still not ringing. */
export type HeldBackReason = "not_persistent" | "low_confidence";

export interface FeatureScore {
  channel: number;
  feature_code: string;
  /** Null when nothing could be scored. Check `is_scored`, not this. */
  score: number | null;
  band: AnomalyBand | null;
  is_scored: boolean;
  /**
   * Signed. A bearing band that collapses is as interesting as one that
   * climbs, and a magnitude loses the difference between a machine getting
   * worse and a sensor falling off.
   */
  z_score: number | null;
  /**
   * How much the comparison is worth — separate from how unusual the reading
   * is, and never multiplied into it. A 90 from a baseline of thirteen
   * captures and a 45 from one of two hundred are not the same finding.
   */
  confidence: number;
  baseline_version: number | null;
  mode_id: string | null;
  reason: string | null;
  contributions: Record<string, unknown>;
}

export interface CaptureScores {
  upload_id: string;
  sensor_id: string;
  scored: number;
  unscored: number;
  mode_id: string | null;
  mode_label: string | null;
  /** Null when nothing could be scored — not a zero-scoring feature. */
  worst: FeatureScore | null;
  scores: FeatureScore[];
}

/**
 * One capture that has actually been scored.
 *
 * The upload's own `features_status` cannot answer this — 157 uploads on
 * this platform say "pending" while 120 of them carry scores, because that
 * column is written by the ingest path and the scores were also written by
 * backfill scripts. The score table is the only thing that knows.
 */
export interface ScoredCapture {
  upload_id: string;
  created_at: string;
  scored: number;
  unscored: number;
  worst_score: number | null;
  worst_band: AnomalyBand | null;
  mode_label: string | null;
}

export interface DetectorDriver {
  feature: string;
  /** Share of the residual this feature accounts for, 0–1. */
  share: number;
}

export interface DetectorScore {
  channel: number;
  method: "isolation_forest" | "pca_residual";
  score: number | null;
  is_scored: boolean;
  raw: number | null;
  /** Empty for Isolation Forest, which does not decompose. */
  drivers: DetectorDriver[];
  training_samples: number | null;
  reason: string | null;
}

export interface Alarm {
  channel: number;
  feature_code: string;
  score: number | null;
  band: AnomalyBand | null;
  confidence: number | null;
  /** Consecutive captures past the line, and how many this machine needs. */
  run_length: number;
  required: number;
  /**
   * When this fault *first* started, kept across a dip below the line. The
   * one fact here that cannot be recomputed from the scores, and the one a
   * maintenance engineer most wants.
   */
  first_alarmed_at: string | null;
  last_alarmed_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  reason: string | null;
}

export interface HeldBackAlarm extends Alarm {
  held_back: HeldBackReason;
}

export interface AlarmSummary {
  sensor_id: string;
  profile: SensitivityProfile;
  alarming: number;
  held_back: number;
  alarms: Alarm[];
  /** Past the line, not acted on. Never includes features that are simply quiet. */
  suppressed: HeldBackAlarm[];
}

export interface Sensitivity {
  equipment_id: string;
  profile: SensitivityProfile;
  /** The four numbers the profile sets, so a screen can show what it does. */
  score_threshold: number;
  persistence: number;
  min_confidence: number;
  baseline_days: number | null;
  expert_overrides: Record<string, number>;
  updated_by: string | null;
  updated_at: string | null;
}

export interface OperatingMode {
  id: string;
  equipment_id: string;
  label: string;
  rpm_min: number | null;
  rpm_max: number | null;
  load_min: number | null;
  load_max: number | null;
  /** "configured" by a person, or "discovered" from the equipment record. */
  source: "configured" | "discovered";
  is_active: boolean;
  notes: string | null;
}

export interface CaptureMode {
  upload_id: string;
  label: string;
  mode_id: string | null;
  /** True when nothing matched. The label is then "unknown"; the two always agree. */
  is_unknown: boolean;
  confidence: number;
  shaft_hz: number | null;
  shaft_source: string | null;
  stability: string | null;
  reason: string | null;
}
