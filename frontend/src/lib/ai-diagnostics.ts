import type { SensorExportRow } from "@/api/sensorExport";
import type { ThresholdRule } from "@/types/thresholds";
import {
  getFeatureDefinition,
  resolveVibrationFeatureKey,
  type VibrationFeatureKey,
} from "@/lib/vibration-features";

/**
 * Diagnostic engine behind the AI Analysis page.
 *
 * Everything here runs on the rows `/api/v1/sensors/{id}/export` already
 * returns — the same features the Status (Health) tab grades — so the page
 * needs no new endpoint and can never disagree with the rest of the app about
 * what a capture measured.
 *
 * The rules are the classical machinery-diagnostics patterns (1X dominance,
 * 2X for misalignment, harmonic spread for looseness, envelope and kurtosis for
 * rolling-element defects). They are heuristics with published thresholds, not
 * a trained model, so every finding carries the numbers it fired on and an
 * analyst can overrule it.
 */

export type CaptureStatus = "normal" | "warning" | "critical" | "no_baseline" | "no_data";

const clamp01 = (value: number): number => (value < 0 ? 0 : value > 1 ? 1 : value);

/** Ratio of a value to a reference, or null when the reference is unusable. */
function ratio(value: number | undefined, reference: number | undefined): number | null {
  if (value === undefined || reference === undefined) return null;
  if (!Number.isFinite(value) || !Number.isFinite(reference) || Math.abs(reference) < 1e-12) {
    return null;
  }
  return value / reference;
}

export function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Median absolute deviation, scaled to match a standard deviation on normal
 * data. Preferred over a plain standard deviation because a handful of captures
 * is all the history most sensors have, and one bad capture would otherwise
 * inflate the spread enough to hide every later rise.
 */
export function madStdDev(values: number[], med: number): number {
  if (values.length < 2) return 0;
  const deviations = values.map((v) => Math.abs(v - med));
  return median(deviations) * 1.4826;
}

/** Robust z-score of `value` against `history`; 0 when history is too thin. */
export function robustZ(value: number, history: number[]): number {
  if (history.length < 3 || !Number.isFinite(value)) return 0;
  const med = median(history);
  const scale = madStdDev(history, med);
  // A perfectly flat history has a MAD of 0; fall back to relative change so a
  // step away from a constant signal still registers instead of dividing by 0.
  if (scale < 1e-12) {
    if (Math.abs(med) < 1e-12) return 0;
    return ((value - med) / Math.abs(med)) * 3;
  }
  return (value - med) / scale;
}

export interface AiCapture {
  uploadId: string;
  channel: number;
  observedAt: string;
  timeMs: number;
  rotationRpm: number | null;
  features: Partial<Record<VibrationFeatureKey, number>>;
  statuses: Partial<Record<VibrationFeatureKey, CaptureStatus>>;
  statusCounts: Record<CaptureStatus, number>;
  worstStatus: CaptureStatus;
}

export interface AiDataset {
  channels: number[];
  captures: AiCapture[];
}

const STATUS_RANK: Record<CaptureStatus, number> = {
  no_data: 0,
  no_baseline: 1,
  normal: 2,
  warning: 3,
  critical: 4,
};

function emptyStatusCounts(): Record<CaptureStatus, number> {
  return { normal: 0, warning: 0, critical: 0, no_baseline: 0, no_data: 0 };
}

function normalizeStatus(raw: string): CaptureStatus {
  if (raw === "normal" || raw === "warning" || raw === "critical" || raw === "no_baseline") {
    return raw;
  }
  return "no_data";
}

/**
 * Collapse the flat export into one record per (capture, channel).
 *
 * The export ships one row per feature, so a 2-channel capture with 10 features
 * arrives as 20 rows; every rule below wants them as a single vector.
 */
export function buildAiDataset(rows: SensorExportRow[]): AiDataset {
  const byKey = new Map<string, AiCapture>();
  const channels = new Set<number>();

  for (const row of rows) {
    if (row.channel === "" || !row.feature_code) continue;
    const featureKey = resolveVibrationFeatureKey(row.feature_code);
    if (!featureKey) continue;

    const channel = Number(row.channel);
    const key = `${row.upload_id}::${channel}`;
    channels.add(channel);

    let capture = byKey.get(key);
    if (!capture) {
      const observedAt = row.observed_at || row.measured_at || row.created_at;
      capture = {
        uploadId: row.upload_id,
        channel,
        observedAt,
        timeMs: new Date(observedAt).getTime(),
        rotationRpm: row.rotation_speed_rpm === "" ? null : Number(row.rotation_speed_rpm),
        features: {},
        statuses: {},
        statusCounts: emptyStatusCounts(),
        worstStatus: "no_data",
      };
      byKey.set(key, capture);
    }

    if (row.value !== "" && Number.isFinite(Number(row.value))) {
      capture.features[featureKey] = Number(row.value);
    }
    const status = normalizeStatus(row.status);
    capture.statuses[featureKey] = status;
    capture.statusCounts[status] += 1;
    if (STATUS_RANK[status] > STATUS_RANK[capture.worstStatus]) {
      capture.worstStatus = status;
    }
  }

  const captures = [...byKey.values()]
    .filter((c) => Number.isFinite(c.timeMs))
    .sort((a, b) => a.timeMs - b.timeMs);

  return { channels: [...channels].sort((a, b) => a - b), captures };
}

/** The captures for one channel, oldest first. */
export function channelSeries(dataset: AiDataset, channel: number): AiCapture[] {
  return dataset.captures.filter((c) => c.channel === channel);
}

export type FaultId = "unbalance" | "misalignment" | "looseness" | "bearing" | "broadband";
export type FaultSeverity = "watch" | "elevated" | "severe";

export interface FaultEvidence {
  label: string;
  value: string;
  note: string;
}

export interface FaultFinding {
  id: FaultId;
  label: string;
  /** 0-1. Below MIN_CONFIDENCE the finding is dropped rather than shown. */
  confidence: number;
  severity: FaultSeverity;
  summary: string;
  evidence: FaultEvidence[];
  recommendation: string;
  basis: string;
}

/** Below this the pattern is indistinguishable from normal scatter. */
const MIN_CONFIDENCE = 0.25;

function severityOf(confidence: number): FaultSeverity {
  if (confidence >= 0.7) return "severe";
  if (confidence >= 0.45) return "elevated";
  return "watch";
}

function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000 || (value !== 0 && Math.abs(value) < 0.01)) {
    return value.toExponential(1);
  }
  return value.toFixed(digits);
}

function historyOf(history: AiCapture[], key: VibrationFeatureKey): number[] {
  return history
    .map((c) => c.features[key])
    .filter((v): v is number => v !== undefined && Number.isFinite(v));
}

/**
 * Rise of a feature over its own history median, as a 0-1 score where
 * `fullRise` (a fraction, e.g. 0.6 for +60%) scores 1.
 */
function riseScore(
  latest: AiCapture,
  history: AiCapture[],
  key: VibrationFeatureKey,
  fullRise: number
): { score: number; ratio: number | null } {
  const values = historyOf(history, key);
  const current = latest.features[key];
  if (current === undefined || values.length < 2) return { score: 0, ratio: null };
  const r = ratio(current, median(values));
  if (r === null) return { score: 0, ratio: null };
  return { score: clamp01((r - 1) / fullRise), ratio: r };
}

/**
 * Rank the fault patterns the latest capture matches.
 *
 * `history` is every earlier capture on the same channel. The rules compare
 * against the machine's own past rather than an absolute limit, because the
 * features are in scaled engineering units whose absolute size depends on the
 * sensor and how it is mounted.
 */
export function diagnoseCapture(latest: AiCapture, history: AiCapture[]): FaultFinding[] {
  const f = latest.features;
  const a1 = f.amplitude_1x;
  const a2 = f.amplitude_2x;
  const a3 = f.amplitude_3x;
  const r2 = ratio(a2, a1);
  const r3 = ratio(a3, a1);

  const findings: FaultFinding[] = [];

  // Unbalance: 1X dominant, harmonics small, 1X rising.
  if (a1 !== undefined && r2 !== null && r3 !== null) {
    const dominance = clamp01((0.5 - Math.max(r2, r3)) / 0.4);
    const rise = riseScore(latest, history, "amplitude_1x", 1.0);
    const confidence = 0.6 * dominance + 0.4 * rise.score;
    if (confidence >= MIN_CONFIDENCE) {
      findings.push({
        id: "unbalance",
        label: "Rotor unbalance",
        confidence,
        severity: severityOf(confidence),
        summary:
          "The spectrum is dominated by the running speed with little harmonic content — the signature of a mass unbalance on the rotor.",
        evidence: [
          { label: "1X amplitude", value: fmt(a1, 4), note: "running-speed peak" },
          {
            label: "2X / 1X",
            value: fmt(r2),
            note: "below 0.5 keeps unbalance ahead of misalignment",
          },
          { label: "3X / 1X", value: fmt(r3), note: "below 0.5 argues against looseness" },
          {
            label: "1X vs history",
            value: rise.ratio === null ? "—" : `${fmt(rise.ratio)}×`,
            note: "against the median of earlier captures",
          },
        ],
        recommendation:
          "Inspect the rotor for material build-up, erosion or a lost balance weight, then trim-balance in place if 1X stays dominant after cleaning.",
        basis: "1X dominance with 2X and 3X below half of 1X.",
      });
    }
  }

  // Misalignment: strong 2X, often with 3X alongside it.
  if (r2 !== null) {
    const twoX = clamp01((r2 - 0.4) / 0.6);
    const threeXSupport = r3 === null ? 0 : clamp01((r3 - 0.3) / 0.7);
    const confidence = 0.75 * twoX + 0.25 * threeXSupport;
    if (confidence >= MIN_CONFIDENCE) {
      findings.push({
        id: "misalignment",
        label: "Shaft misalignment",
        confidence,
        severity: severityOf(confidence),
        summary:
          "The second harmonic carries a large share of the running-speed energy, which is how a coupled misalignment presents.",
        evidence: [
          { label: "2X / 1X", value: fmt(r2), note: "above 0.5 is the classic misalignment marker" },
          { label: "3X / 1X", value: fmt(r3), note: "a raised 3X points at angular misalignment" },
          { label: "2X amplitude", value: fmt(a2, 4), note: "twice running speed" },
        ],
        recommendation:
          "Check coupling condition and soft foot, then laser-align the train. Re-measure axially — misalignment shows a high axial 1X/2X that a radial sensor understates.",
        basis: "2X above 40% of 1X, weighted up when 3X is also raised.",
      });
    }
  }

  // Looseness: harmonic spread plus a rising noise floor.
  if (r2 !== null && r3 !== null) {
    const spread = clamp01((r2 + r3 - 0.6) / 0.9);
    const noiseNow = f.noise_floor;
    const noiseZ = noiseNow === undefined ? 0 : robustZ(noiseNow, historyOf(history, "noise_floor"));
    const noiseRise = clamp01(noiseZ / 4);
    const confidence = 0.6 * spread + 0.4 * noiseRise;
    if (confidence >= MIN_CONFIDENCE) {
      findings.push({
        id: "looseness",
        label: "Mechanical looseness",
        confidence,
        severity: severityOf(confidence),
        summary:
          "Energy is spread across several running-speed harmonics and the broadband floor has lifted — the pattern of a loose fit or a slack fastening.",
        evidence: [
          {
            label: "2X + 3X vs 1X",
            value: fmt(r2 + r3),
            note: "harmonic energy relative to running speed",
          },
          { label: "Noise floor", value: fmt(noiseNow, 1), note: "dB" },
          {
            label: "Noise floor z",
            value: fmt(noiseZ, 1),
            note: "deviation from this sensor's own history",
          },
        ],
        recommendation:
          "Check hold-down bolt torque, base grouting and bearing-housing fits. Looseness rarely improves on its own and it masks the faults underneath it — clear it first, then re-measure.",
        basis: "Combined 2X+3X above 60% of 1X together with a lifted noise floor.",
      });
    }
  }

  // Rolling-element bearing defect: envelope, kurtosis, crest factor.
  {
    const envelope = riseScore(latest, history, "envelope_rms", 0.6);
    const kurtosis = f.kurtosis;
    const crest = f.crest_factor;
    // Excess kurtosis: a clean random signal sits near 0, impacting above 1.
    const kurtScore = kurtosis === undefined ? 0 : clamp01((kurtosis - 1) / 3);
    const crestScore = crest === undefined ? 0 : clamp01((crest - 3.5) / 3);
    const confidence = 0.45 * envelope.score + 0.35 * kurtScore + 0.2 * crestScore;
    if (confidence >= MIN_CONFIDENCE) {
      findings.push({
        id: "bearing",
        label: "Rolling-element bearing defect",
        confidence,
        severity: severityOf(confidence),
        summary:
          "The demodulated envelope has grown and the waveform has turned impulsive — early bearing damage shows here long before it reaches overall RMS.",
        evidence: [
          {
            label: "Envelope RMS vs history",
            value: envelope.ratio === null ? "—" : `${fmt(envelope.ratio)}×`,
            note: "demodulated high-frequency energy",
          },
          { label: "Kurtosis", value: fmt(kurtosis), note: "excess kurtosis; above 1 is impulsive" },
          { label: "Crest factor", value: fmt(crest), note: "above 3.5 indicates impacting" },
        ],
        recommendation:
          "Take an envelope spectrum and look for BPFO/BPFI/BSF families and their sidebands. Confirm lubrication, then plan the bearing change on the trend rather than on one capture.",
        basis: "Envelope RMS rise weighted with excess kurtosis and crest factor.",
      });
    }
  }

  // Broadband deterioration: the overall level climbing without a clear home.
  {
    const rms = riseScore(latest, history, "rms", 0.5);
    const band = riseScore(latest, history, "fft_band_energy", 0.8);
    const confidence = 0.6 * rms.score + 0.4 * band.score;
    if (confidence >= MIN_CONFIDENCE) {
      findings.push({
        id: "broadband",
        label: "Broadband level rise",
        confidence,
        severity: severityOf(confidence),
        summary:
          "Overall vibration has climbed against this sensor's own history without settling on one harmonic — treat it as deterioration until a spectrum names the source.",
        evidence: [
          {
            label: "RMS vs history",
            value: rms.ratio === null ? "—" : `${fmt(rms.ratio)}×`,
            note: "overall level",
          },
          {
            label: "0-500 Hz energy vs history",
            value: band.ratio === null ? "—" : `${fmt(band.ratio)}×`,
            note: "in-band spectral energy",
          },
        ],
        recommendation:
          "Compare the FFT against the baseline capture on the Vibration Analysis page to find which band moved, and shorten the measurement interval until the trend flattens.",
        basis: "RMS and 0-500 Hz band energy rising together over the capture history.",
      });
    }
  }

  return findings.sort((a, b) => b.confidence - a.confidence);
}

export type AnomalyLevel = "normal" | "borderline" | "anomalous";

export interface AnomalyPoint {
  uploadId: string;
  observedAt: string;
  timeMs: number;
  /** Largest robust z across features, against everything measured before it. */
  score: number;
  driver: VibrationFeatureKey | null;
  level: AnomalyLevel;
}

const ANOMALY_FEATURES: VibrationFeatureKey[] = [
  "rms",
  "peak",
  "crest_factor",
  "kurtosis",
  "fft_band_energy",
  "amplitude_1x",
  "amplitude_2x",
  "amplitude_3x",
  "envelope_rms",
  "noise_floor",
];

/** Minimum earlier captures before a z-score means anything. */
export const ANOMALY_MIN_HISTORY = 4;

/**
 * Score every capture against the ones before it (an expanding window), so a
 * point is judged only on what was known at the time. Scoring against the whole
 * series would let a later fault drag the reference and hide its own onset.
 */
export function scoreAnomalies(series: AiCapture[]): AnomalyPoint[] {
  return series.map((capture, index) => {
    const history = series.slice(0, index);
    let score = 0;
    let driver: VibrationFeatureKey | null = null;

    if (history.length >= ANOMALY_MIN_HISTORY) {
      for (const key of ANOMALY_FEATURES) {
        const value = capture.features[key];
        if (value === undefined) continue;
        const z = Math.abs(robustZ(value, historyOf(history, key)));
        if (z > score) {
          score = z;
          driver = key;
        }
      }
    }

    return {
      uploadId: capture.uploadId,
      observedAt: capture.observedAt,
      timeMs: capture.timeMs,
      score,
      driver,
      level: score >= 4 ? "anomalous" : score >= 2.5 ? "borderline" : "normal",
    };
  });
}

export interface TrendLimit {
  label: string;
  value: number;
}

export interface TrendPoint {
  timeMs: number;
  value: number;
}

export interface TrendProjection {
  key: VibrationFeatureKey;
  label: string;
  unit: string;
  points: TrendPoint[];
  /** The fitted line as two endpoints, extended to the projection horizon. */
  fit: TrendPoint[];
  slopePerDay: number;
  changePerWeekPct: number | null;
  /** Goodness of fit — below ~0.3 the projection is noise, and is labelled so. */
  r2: number;
  latest: number;
  projected: number;
  horizonDays: number;
  limit: TrendLimit | null;
  daysToLimit: number | null;
}

export const TREND_HORIZON_DAYS = 30;
const MS_PER_DAY = 86_400_000;

/**
 * Least-squares trend of one feature with a straight-line projection.
 *
 * Deliberately linear: with the handful of captures a sensor typically has,
 * anything higher-order fits the noise and projects nonsense.
 */
export function projectFeatureTrend(
  series: AiCapture[],
  key: VibrationFeatureKey,
  limit: TrendLimit | null
): TrendProjection | null {
  const points: TrendPoint[] = series
    .map((c) => ({ timeMs: c.timeMs, value: c.features[key] }))
    .filter((p): p is TrendPoint => p.value !== undefined && Number.isFinite(p.value));

  if (points.length < 3) return null;

  const t0 = points[0].timeMs;
  const xs = points.map((p) => (p.timeMs - t0) / MS_PER_DAY);
  const ys = points.map((p) => p.value);
  const n = xs.length;
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = ys.reduce((a, b) => a + b, 0) / n;

  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - meanX;
    const dy = ys[i] - meanY;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }

  // Every capture landing in the same instant leaves no time axis to fit.
  if (sxx < 1e-12) return null;

  const slope = sxy / sxx;
  const intercept = meanY - slope * meanX;
  const r2 = syy < 1e-12 ? 0 : clamp01((sxy * sxy) / (sxx * syy));

  const lastX = xs[n - 1];
  const latest = ys[n - 1];
  const horizonX = lastX + TREND_HORIZON_DAYS;
  const projected = intercept + slope * horizonX;

  let daysToLimit: number | null = null;
  if (limit && slope > 0 && latest < limit.value) {
    const days = (limit.value - intercept) / slope - lastX;
    // A crossing further out than a couple of years is a straight line's
    // arithmetic, not a forecast — report nothing rather than a false date.
    if (days > 0 && days < 730) daysToLimit = days;
  }

  const def = getFeatureDefinition(key);

  return {
    key,
    label: def.label,
    unit: def.unit,
    points,
    fit: [
      { timeMs: t0, value: intercept },
      { timeMs: t0 + horizonX * MS_PER_DAY, value: projected },
    ],
    slopePerDay: slope,
    changePerWeekPct: Math.abs(meanY) < 1e-12 ? null : ((slope * 7) / Math.abs(meanY)) * 100,
    r2,
    latest,
    projected,
    horizonDays: TREND_HORIZON_DAYS,
    limit,
    daysToLimit,
  };
}

export type HealthBand = "healthy" | "watch" | "warning" | "critical";

export interface HealthDriver {
  label: string;
  penalty: number;
}

export interface HealthAssessment {
  score: number;
  band: HealthBand;
  drivers: HealthDriver[];
  headline: string;
}

export const HEALTH_BAND_LABEL: Record<HealthBand, string> = {
  healthy: "Healthy",
  watch: "Watch",
  warning: "Warning",
  critical: "Critical",
};

/**
 * One 0-100 number for the channel, with the deductions that produced it.
 *
 * The drivers are part of the output on purpose: a score nobody can take apart
 * is a score nobody acts on.
 */
export function assessHealth(
  latest: AiCapture,
  findings: FaultFinding[],
  anomaly: AnomalyPoint | null
): HealthAssessment {
  const drivers: HealthDriver[] = [];

  const criticalCount = latest.statusCounts.critical;
  const warningCount = latest.statusCounts.warning;

  if (criticalCount) {
    drivers.push({
      label: `${criticalCount} feature${criticalCount > 1 ? "s" : ""} over the critical limit`,
      penalty: Math.min(60, criticalCount * 20),
    });
  }
  if (warningCount) {
    drivers.push({
      label: `${warningCount} feature${warningCount > 1 ? "s" : ""} in warning`,
      penalty: Math.min(30, warningCount * 8),
    });
  }

  const top = findings[0];
  if (top) {
    drivers.push({
      label: `${top.label} pattern at ${Math.round(top.confidence * 100)}% confidence`,
      penalty: Math.round(top.confidence * 22),
    });
  }

  if (anomaly && anomaly.level !== "normal") {
    drivers.push({
      label:
        anomaly.level === "anomalous"
          ? "Latest capture is a statistical outlier against its own history"
          : "Latest capture is drifting from its own history",
      penalty: anomaly.level === "anomalous" ? 12 : 6,
    });
  }

  const penalty = drivers.reduce((sum, d) => sum + d.penalty, 0);
  const score = Math.max(0, Math.min(100, Math.round(100 - penalty)));
  const band: HealthBand =
    score >= 85 ? "healthy" : score >= 65 ? "watch" : score >= 40 ? "warning" : "critical";

  const headline = !drivers.length
    ? "No fault pattern stands out and every graded feature is inside its limit."
    : top
      ? `${top.label} is the strongest pattern in the latest capture.`
      : "Graded features are outside their limits without a single dominant pattern.";

  return { score, band, drivers, headline };
}

export interface ResolvedLimit {
  normalMax: number | null;
  warningMax: number | null;
  normalLabel: string;
  warningLabel: string;
}

/**
 * Absolute limits per feature for one channel, from the threshold rules.
 *
 * Only `absolute_max` rules are usable here — a percent-of-baseline rule has no
 * fixed value a raw trend line can be projected onto, so those are skipped
 * rather than misread as engineering units.
 *
 * Scoping follows the same precedence the evaluator uses: a rule named for this
 * machine type beats a site-wide one, and a rule named for this channel beats
 * the rule it would otherwise inherit.
 */
export function resolveAbsoluteLimits(
  rules: ThresholdRule[],
  channel: number,
  machineType: string | null
): Map<VibrationFeatureKey, ResolvedLimit> {
  const out = new Map<VibrationFeatureKey, ResolvedLimit>();
  const specificity = new Map<VibrationFeatureKey, number>();

  for (const rule of rules) {
    if (!rule.is_active || rule.rule_type !== "absolute_max") continue;
    // A rule scoped to another channel or machine type says nothing about this one.
    if (rule.channel !== null && rule.channel !== channel) continue;
    if (rule.machine_type !== null && rule.machine_type !== machineType) continue;

    const key = resolveVibrationFeatureKey(rule.feature_code);
    if (!key) continue;

    const rank = (rule.machine_type !== null ? 2 : 0) + (rule.channel !== null ? 1 : 0);
    if (rank < (specificity.get(key) ?? -1)) continue;

    specificity.set(key, rank);
    out.set(key, {
      normalMax: rule.normal_max,
      warningMax: rule.warning_max,
      normalLabel: rule.limit_labels.normal_max ?? "Caution limit",
      warningLabel: rule.limit_labels.warning_max ?? "Warning limit",
    });
  }

  return out;
}

/** The limit a trend should be projected onto: the first one it would cross. */
export function trendLimitFor(limit: ResolvedLimit | undefined): TrendLimit | null {
  if (!limit) return null;
  if (limit.normalMax !== null) return { label: limit.normalLabel, value: limit.normalMax };
  if (limit.warningMax !== null) return { label: limit.warningLabel, value: limit.warningMax };
  return null;
}
