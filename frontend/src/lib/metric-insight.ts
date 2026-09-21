import type { HealthMetricTrend, HealthStatusLevel } from "@/types/health-status";
import type { StatusTone } from "@/lib/status-box";
import { formatHealthMetricDisplay } from "@/lib/health-trend-option";

/**
 * Per-graph reading: what one metric's trace is doing, what it means, and what
 * to do about it.
 *
 * The narrative is derived, not retrieved — every sentence below is produced
 * from the 32 segment values the card already plots, plus the limits that
 * graded it. Nothing is guessed and nothing leaves the browser.
 *
 * The interpretations are the standard machinery-diagnostics readings of each
 * feature (crest factor under 1.41 means a flattened waveform, excess kurtosis
 * above 1 means impacting, and so on). They are rules with published meanings,
 * which is why each card shows the numbers it reasoned from.
 */

export interface InsightStat {
  label: string;
  value: string;
  hint?: string;
}

export interface MetricInsight {
  /** One-line verdict, the first thing read. */
  headline: string;
  tone: StatusTone;
  /** One line on what the trace is doing — the stats carry the numbers. */
  behaviour: string;
  stats: InsightStat[];
  /** One line on what the feature measures. */
  meaning: string;
  suggestions: string[];
  /** Limits of this reading — always shown, never buried. */
  caveats: string[];
}

const TONE_BY_STATUS: Record<HealthStatusLevel, StatusTone> = {
  healthy: "healthy",
  warning: "warning",
  danger: "critical",
  neutral: "neutral",
};

/** A pure sine wave's crest factor. Below it the waveform is flat-topped. */
const SINE_CREST = 1.414;

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function stdDev(values: number[], avg: number): number {
  if (values.length < 2) return 0;
  return Math.sqrt(values.reduce((sum, v) => sum + (v - avg) ** 2, 0) / (values.length - 1));
}

/** Least-squares slope of y against x. */
function slope(xs: number[], ys: number[]): number {
  const n = xs.length;
  if (n < 3) return 0;
  const mx = mean(xs);
  const my = mean(ys);
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < n; i += 1) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) ** 2;
  }
  return sxx < 1e-15 ? 0 : sxy / sxx;
}

interface Shape {
  count: number;
  avg: number;
  med: number;
  min: number;
  max: number;
  range: number;
  sd: number;
  /** Spread as a percentage of the feature's own scale. */
  cv: number;
  /** Change across the whole window, in the feature's units. */
  drift: number;
  /** That change as a percentage of the feature's own scale. */
  driftPct: number;
  /**
   * Whether the drift is large enough to be a trend rather than noise. A trace
   * scattering either side of a flat line still fits a line with some slope;
   * without this gate, kurtosis wobbling around zero reports as "climbing".
   */
  driftIsReal: boolean;
  /** Segments more than 3 robust sigma from the median. */
  outliers: number;
}

function describeShape(metric: HealthMetricTrend): Shape | null {
  // Defensive: this runs for every card in the grid, so a single capture with a
  // missing array would otherwise throw and take the whole section down with it.
  const ys = (metric.trendY ?? []).filter((v) => Number.isFinite(v));
  if (ys.length < 3) return null;

  const rawX = metric.trendX ?? [];
  // A short or absent x axis would leave the slope fit dividing by NaN; segment
  // index is a fine stand-in, since the segments are evenly spaced anyway.
  const xs = rawX.length >= ys.length ? rawX.slice(0, ys.length) : ys.map((_, i) => i);
  const avg = mean(ys);
  const med = median(ys);
  const sd = stdDev(ys, avg);
  const min = Math.min(...ys);
  const max = Math.max(...ys);

  // Robust spread, so one spike does not define "normal" for the other 31.
  const deviations = ys.map((v) => Math.abs(v - med));
  const mad = median(deviations) * 1.4826;
  const outliers = mad > 1e-15 ? ys.filter((v) => Math.abs(v - med) / mad > 3).length : 0;

  const windowSpan = xs.length > 1 ? xs[xs.length - 1] - xs[0] : 0;
  const drift = slope(xs, ys) * windowSpan;

  // Percentages need a denominator that means something. The mean is the
  // obvious one and it is wrong for any feature that crosses zero: kurtosis
  // and skew sit near 0 by definition, so dividing by their mean turns
  // ordinary scatter into "2331% variability". Fall back to the feature's own
  // spread when the mean is too small to scale against.
  const scale = Math.max(Math.abs(med), mad, (max - min) / 4, 1e-15);

  return {
    count: ys.length,
    avg,
    med,
    min,
    max,
    range: max - min,
    sd,
    cv: (sd / scale) * 100,
    drift,
    driftPct: (drift / scale) * 100,
    driftIsReal: Math.abs(drift) > 1.5 * sd,
    outliers,
  };
}

interface Interpretation {
  meaning: string;
  /** Reading of the current value, when the feature has a known scale. */
  read?: (value: number, metric: HealthMetricTrend) => string | null;
  /** Actions worth taking regardless of what the trace is doing. */
  baseSuggestions: string[];
}

const INTERPRETATIONS: Record<string, Interpretation> = {
  rms: {
    meaning:
      "Overall energy in the waveform — it moves with almost every fault, so it says something changed, never what.",
    baseSuggestions: [
      "Compare this capture's RMS against the sensor's baseline rather than against an absolute number — mounting and sensitivity set the scale.",
      "If RMS has risen, look at the FFT next: the band that grew is what names the fault.",
    ],
  },
  vrms: {
    meaning:
      "Velocity RMS — the ISO 10816 / 20816 quantity that machine condition zones are written against.",
    baseSuggestions: [
      "Judge this against the ISO zone for the machine's size and mounting class, not against other channels.",
    ],
  },
  peak: {
    meaning:
      "The largest single excursion in the capture — read beside RMS to tell short impacts from a general rise in level.",
    baseSuggestions: [
      "Check peak against RMS — a widening gap between them is an impacting signature worth an envelope spectrum.",
    ],
  },
  crest_factor: {
    meaning:
      "Peak divided by RMS — waveform shape regardless of size: 1.41 is a sine, 3-4 healthy random, higher means impacts.",
    read: (value) => {
      if (value < 1.2) {
        return `At ${value.toFixed(3)} the waveform is flatter than a pure sine's 1.41 — almost certainly the sensor clipping, not the machine.`;
      }
      if (value < SINE_CREST) {
        return `At ${value.toFixed(3)} the waveform sits below a pure sine's 1.41 — suspect clipping, or one strong sinusoid dominating.`;
      }
      if (value > 6) {
        return `At ${value.toFixed(2)} the waveform is strongly impulsive — the classic early bearing-defect or looseness shape.`;
      }
      if (value > 4) {
        return `At ${value.toFixed(2)} the waveform is more impulsive than healthy random vibration, so impacting has likely started.`;
      }
      return `At ${value.toFixed(2)} the waveform shape sits in the normal random-vibration band of roughly 3 to 4.`;
    },
    baseSuggestions: [
      "Crest factor falls again once a bearing defect is advanced — RMS rises to meet the peaks. Never read it alone; read it beside RMS.",
    ],
  },
  kurtosis: {
    meaning:
      "How impulsive the signal is — excess kurtosis, so clean noise sits near 0 and above 1 means sharp repetitive events.",
    read: (value) => {
      if (value > 3) {
        return `At ${value.toFixed(2)} the signal is strongly impulsive — the shape bearing damage, cavitation or looseness makes.`;
      }
      if (value > 1) {
        return `At ${value.toFixed(2)} there is mild impulsiveness — worth an envelope spectrum to place it.`;
      }
      if (value < -0.5) {
        return `At ${value.toFixed(2)} the distribution is flatter than random noise — one or two strong sinusoids dominate, rather than impacts.`;
      }
      return `At ${value.toFixed(2)} the amplitude distribution is essentially Gaussian — no impacting in this capture.`;
    },
    baseSuggestions: [
      "Kurtosis is the earliest of the time-domain indicators — track its trend across captures, not its value in one.",
    ],
  },
  skew: {
    meaning:
      "Asymmetry of the amplitude distribution — near zero is healthy, a bias points at DC offset, a rub, or mounting.",
    baseSuggestions: ["Check the sensor's DC offset and mounting before treating skew as a machine fault."],
  },
  fft_band_energy: {
    meaning:
      "Total spectral energy in the 0-500 Hz band, where shaft-rate faults live — a level, not a diagnosis.",
    baseSuggestions: [
      "When this rises, open the FFT and compare it against the baseline spectrum — the line that grew is the fault.",
    ],
  },
  amplitude_1x: {
    meaning:
      "Amplitude at running speed — where rotor unbalance appears, especially when it dominates the harmonics.",
    baseSuggestions: [
      "Compare 1X against 2X and 3X — the ratio is what separates unbalance from misalignment and looseness.",
      "If 1X is rising, check the rotor for build-up, erosion or a lost balance weight before planning a balance job.",
    ],
  },
  amplitude_2x: {
    meaning:
      "Amplitude at twice running speed — a large 2X beside 1X is the classic coupled-misalignment marker.",
    baseSuggestions: [
      "Take an axial measurement — misalignment understates itself on a radial sensor.",
      "Check coupling condition and soft foot before scheduling an alignment.",
    ],
  },
  amplitude_3x: {
    meaning:
      "Amplitude at three times running speed — raised alongside 2X it points at angular misalignment or looseness.",
    baseSuggestions: [
      "Check hold-down bolt torque and bearing-housing fits — looseness masks the faults underneath it, so clear it first.",
    ],
  },
  envelope_rms: {
    meaning:
      "Energy in the demodulated envelope — the earliest reliable bearing indicator, moving long before RMS does.",
    baseSuggestions: [
      "If this is rising, take an envelope spectrum and look for BPFO/BPFI/BSF families and their sidebands.",
      "Confirm lubrication first — a dry bearing raises envelope energy without being damaged yet.",
    ],
  },
  noise_floor: {
    meaning:
      "The broadband floor the spectrum sits on — it lifts with looseness, cavitation, turbulence and electrical noise.",
    baseSuggestions: [
      "Rule out the instrument first: cable routing, grounding and mounting raise the floor as readily as the machine does.",
    ],
  },
  temperature: {
    meaning:
      "Sensor-reported temperature — a slow indicator, but good corroboration for a bearing or lubrication finding.",
    baseSuggestions: ["Read temperature against ambient and load, not as an absolute."],
  },
  saturation: {
    meaning:
      "How close the input stage came to its range — near full scale the waveform clipped and every feature is understated.",
    baseSuggestions: ["If saturation is high, lower the sensitivity or range and re-capture before trusting any other feature."],
  },
  transients: {
    meaning:
      "A count of short-lived events in the capture — impacts, knocks and spikes that do not repeat at a steady rate.",
    baseSuggestions: ["Correlate transients with process events before treating them as a machine fault."],
  },
  battery_health: {
    meaning: "Remaining capacity of the sensor's battery — an instrument reading, not a machine one.",
    baseSuggestions: ["Schedule a battery change before the sensor starts missing captures."],
  },
};

const GENERIC: Interpretation = {
  meaning: "A measured feature of this capture, trended across its segments.",
  baseSuggestions: ["Compare this against the sensor's own baseline rather than an absolute number."],
};

/** The feature's display name, without the "Trend" suffix the series carries. */
export function metricName(metric: HealthMetricTrend): string {
  return (metric.label ?? "This feature").replace(/\s+Trend$/i, "");
}

function formatValue(metric: HealthMetricTrend, value: number): string {
  // "-" is how the catalogue spells "dimensionless"; printed literally it
  // reads as a minus sign hanging off the number ("1.209 -").
  const unit = metric.unit === "-" ? "" : metric.unit;
  return formatHealthMetricDisplay(value, unit);
}

/** How close the current reading sits to the limit that would trip it. */
function headroom(metric: HealthMetricTrend): InsightStat | null {
  const limit = metric.dangerThreshold ?? metric.warningThreshold ?? metric.normalThreshold;
  if (limit === undefined || metric.value === null || !Number.isFinite(limit) || limit === 0) {
    return null;
  }
  const pct = (metric.value / limit) * 100;
  return {
    label: "Of limit used",
    value: `${pct.toFixed(0)}%`,
    hint: `limit ${formatValue(metric, limit)}`,
  };
}

/**
 * The single most notable thing the trace does, in one sentence.
 *
 * Only one line is shown, so the branches are ordered by how much they should
 * change what the reader does next: spikes and drift outrank plain scatter,
 * which the Variability tile already states as a number.
 */
function describeTrace(metric: HealthMetricTrend, shape: Shape, drifting: boolean): string {
  if (shape.outliers > 0) {
    return `${shape.outliers} of ${shape.count} segments spike above the rest, peaking at ${formatValue(metric, shape.max)} against a typical ${formatValue(metric, shape.med)}.`;
  }
  if (drifting) {
    const direction = shape.driftPct > 0 ? "climbs" : "falls";
    return `The trace ${direction} steadily through the capture, by about ${Math.abs(shape.driftPct).toFixed(0)}% end to end — the machine was not at steady state.`;
  }
  if (shape.cv >= 25) {
    return `The trace is highly unstable — ${shape.cv.toFixed(0)}% scatter around its own scale, with no direction to it.`;
  }
  if (shape.cv >= 10) {
    return `The trace swings ${shape.cv.toFixed(0)}% around its own scale — either the load is not steady or the signal carries modulation.`;
  }
  if (shape.cv >= 3) {
    return `The trace varies mildly, ${shape.cv.toFixed(1)}% around its own scale — normal scatter for a machine under steady load.`;
  }
  return `The trace is steady across the capture — only ${shape.cv.toFixed(1)}% spread around its own scale.`;
}

export function buildMetricInsight(
  metric: HealthMetricTrend,
  channelLabel: string
): MetricInsight {
  const interpretation = INTERPRETATIONS[metric.key] ?? GENERIC;
  const tone = TONE_BY_STATUS[metric.status];
  const shape = describeShape(metric);

  if (!metric.available || !shape) {
    return {
      headline: "Not enough data in this capture to read a trend.",
      tone: "neutral",
      behaviour:
        "This feature was not computed for the selected capture, so there is no trace to interpret.",
      stats: [],
      meaning: interpretation.meaning,
      suggestions: [
        "Re-upload the capture so feature extraction runs again, then reopen this card.",
      ],
      caveats: [],
    };
  }

  const drifting = shape.driftIsReal && Math.abs(shape.driftPct) >= 10;

  // One line, not a list. The stat tiles below already carry variability, drift
  // and spike counts as numbers, so repeating them in prose was the bulk of the
  // reading without being the useful part of it. Where a feature has a known
  // scale, what its current value means outranks how the trace wobbled.
  const read = metric.value !== null ? interpretation.read?.(metric.value, metric) : null;
  const behaviour = read ?? describeTrace(metric, shape, drifting);

  // --- Stats ---------------------------------------------------------------
  const stats: InsightStat[] = [
    { label: "Latest", value: metric.value !== null ? formatValue(metric, metric.value) : "—" },
    { label: "Capture mean", value: formatValue(metric, shape.avg) },
    {
      label: "Range",
      value: formatValue(metric, shape.range),
      hint: `${formatValue(metric, shape.min)} to ${formatValue(metric, shape.max)}`,
    },
    {
      label: "Variability",
      value: `${shape.cv.toFixed(1)}%`,
      hint: `± ${formatValue(metric, shape.sd)}`,
    },
    {
      label: "Drift",
      value: `${shape.driftPct >= 0 ? "+" : ""}${shape.driftPct.toFixed(0)}%`,
      hint: shape.driftIsReal ? "across the capture" : "within the noise",
    },
    { label: "Spiking segments", value: `${shape.outliers} of ${shape.count}` },
  ];

  const limitStat = headroom(metric);
  if (limitStat) stats.push(limitStat);

  // --- Suggestions ---------------------------------------------------------
  const suggestions: string[] = [];

  if (metric.status === "danger") {
    suggestions.push(
      `This feature is outside its limit on ${channelLabel}. Confirm it repeats on the next capture before acting — one capture is an observation, two is a trend.`
    );
  } else if (metric.status === "warning") {
    suggestions.push(
      `This feature has crossed its caution limit on ${channelLabel}. Shorten the measurement interval and watch whether it keeps climbing.`
    );
  }

  if (shape.outliers > 0) {
    suggestions.push(
      "Open the raw waveform and look at the spiking segments directly — a genuine impact and an electrical glitch look identical in a trend line but nothing alike in the waveform."
    );
  }
  if (drifting) {
    suggestions.push(
      "Re-capture once the machine is at steady state; features computed across a changing speed or load are not comparable with the baseline."
    );
  }
  if (shape.cv >= 25) {
    suggestions.push(
      "Take a longer capture, or several. With this much scatter the single reported value depends heavily on where the capture happened to start."
    );
  }

  suggestions.push(...interpretation.baseSuggestions);

  // --- Headline ------------------------------------------------------------
  let headline: string;
  if (metric.status === "danger") {
    headline = `${metricName(metric)} is outside its limit and needs attention.`;
  } else if (metric.status === "warning") {
    headline = `${metricName(metric)} has crossed its caution limit — worth watching.`;
  } else if (shape.outliers > 0) {
    headline = `Inside its limits, but ${shape.outliers} segment${shape.outliers > 1 ? "s" : ""} spike above the rest.`;
  } else if (drifting) {
    headline = "Inside its limits, but drifting through the capture rather than holding steady.";
  } else if (shape.cv < 3) {
    headline = "Steady and inside its limits — nothing in this capture to act on.";
  } else {
    headline = "Inside its limits, with normal segment-to-segment variation.";
  }

  const caveats = [
    `Read from the ${shape.count} segments of this single capture on ${channelLabel} — it describes one moment, not a history. The Trend tab is where a direction over time shows.`,
  ];
  if (!metric.normalThreshold && !metric.warningThreshold && !metric.dangerThreshold) {
    caveats.push(
      "No limit is configured for this feature, so the status beside it reflects behaviour only, not a threshold."
    );
  }

  return { headline, tone, behaviour, stats, meaning: interpretation.meaning, suggestions, caveats };
}
