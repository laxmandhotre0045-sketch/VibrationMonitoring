/**
 * Every feature the platform computes, grouped the way the screens read them.
 *
 * This list mirrors `FEATURE_CODES` in the backend's `feature_extraction.py`
 * and has no other reason to hold the number of entries it does — a contract
 * test next door fails if the two drift apart. Drop one and the Settings grid
 * quietly loses a column; add one the backend never sends and the Status tab
 * shows a permanent "no baseline" row for a number nobody computes.
 *
 * Ordered by category rather than by the backend's positional list, because the
 * Status tab and the Settings grid both render it in category blocks. The four
 * categories are the same four the module started with; the features added
 * since are sorted into them rather than given new ones.
 */
export type VibrationFeatureKey =
  | "rms"
  | "peak"
  | "crest_factor"
  | "kurtosis"
  | "peak_to_peak"
  | "std_dev"
  | "skewness"
  | "impulse_factor"
  | "shape_factor"
  | "clearance_factor"
  | "burst_count"
  | "shock_index"
  | "modulation_index"
  | "rms_change_short"
  | "rms_change_long"
  | "zero_crossing_rate"
  | "dc_offset"
  | "fft_band_energy"
  | "amplitude_1x"
  | "amplitude_2x"
  | "amplitude_3x"
  | "dominant_frequency"
  | "dominant_prominence"
  | "harmonic_count"
  | "harmonic_energy_ratio"
  | "sideband_spacing"
  | "sideband_energy_ratio"
  | "spectral_centroid"
  | "spectral_spread"
  | "spectral_entropy"
  | "broadband_noise"
  | "haystack_score"
  | "narrowband_ratio"
  | "peak_drift"
  | "envelope_rms"
  | "ftf_band_energy"
  | "bsf_band_energy"
  | "bpfo_band_energy"
  | "bpfi_band_energy"
  | "bearing_harmonic_energy"
  | "envelope_peak"
  | "envelope_kurtosis"
  | "demodulated_peak_prominence"
  | "repetition_impact_frequency"
  | "resonance_band_energy"
  | "noise_floor";

export type VibrationFeatureCategory =
  | "time_domain"
  | "frequency_domain"
  | "envelope"
  | "noise";

export interface VibrationFeatureDefinition {
  key: VibrationFeatureKey;
  label: string;
  unit: string;
  category: VibrationFeatureCategory;
}

export const VIBRATION_FEATURE_CATALOG: readonly VibrationFeatureDefinition[] = [
  // Time domain — the shape of the waveform itself.
  { key: "rms", label: "RMS", unit: "scaled", category: "time_domain" },
  { key: "peak", label: "Peak", unit: "scaled", category: "time_domain" },
  { key: "crest_factor", label: "Crest Factor", unit: "-", category: "time_domain" },
  { key: "kurtosis", label: "Kurtosis", unit: "-", category: "time_domain" },
  { key: "peak_to_peak", label: "Peak to Peak", unit: "scaled", category: "time_domain" },
  { key: "std_dev", label: "Standard Deviation", unit: "scaled", category: "time_domain" },
  { key: "skewness", label: "Skewness", unit: "-", category: "time_domain" },
  { key: "impulse_factor", label: "Impulse Factor", unit: "-", category: "time_domain" },
  { key: "shape_factor", label: "Shape Factor", unit: "-", category: "time_domain" },
  { key: "clearance_factor", label: "Clearance Factor", unit: "-", category: "time_domain" },
  { key: "burst_count", label: "Burst Count", unit: "-", category: "time_domain" },
  { key: "shock_index", label: "Shock Index", unit: "-", category: "time_domain" },
  { key: "modulation_index", label: "Modulation Index", unit: "-", category: "time_domain" },
  { key: "rms_change_short", label: "RMS Change (short)", unit: "-", category: "time_domain" },
  { key: "rms_change_long", label: "RMS Change (long)", unit: "-", category: "time_domain" },
  { key: "zero_crossing_rate", label: "Zero Crossing Rate", unit: "Hz", category: "time_domain" },
  { key: "dc_offset", label: "DC Offset", unit: "scaled", category: "time_domain" },

  // Frequency domain — where the energy sits in the spectrum.
  { key: "fft_band_energy", label: "FFT Band Energy (0-500 Hz)", unit: "scaled²", category: "frequency_domain" },
  { key: "amplitude_1x", label: "1X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "amplitude_2x", label: "2X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "amplitude_3x", label: "3X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "dominant_frequency", label: "Dominant Frequency", unit: "Hz", category: "frequency_domain" },
  { key: "dominant_prominence", label: "Dominant Prominence", unit: "-", category: "frequency_domain" },
  { key: "harmonic_count", label: "Harmonic Count", unit: "-", category: "frequency_domain" },
  { key: "harmonic_energy_ratio", label: "Harmonic Energy Ratio", unit: "-", category: "frequency_domain" },
  { key: "sideband_spacing", label: "Sideband Spacing", unit: "Hz", category: "frequency_domain" },
  { key: "sideband_energy_ratio", label: "Sideband Energy Ratio", unit: "-", category: "frequency_domain" },
  { key: "spectral_centroid", label: "Spectral Centroid", unit: "Hz", category: "frequency_domain" },
  { key: "spectral_spread", label: "Spectral Spread", unit: "Hz", category: "frequency_domain" },
  { key: "spectral_entropy", label: "Spectral Entropy", unit: "-", category: "frequency_domain" },
  { key: "broadband_noise", label: "Broadband Noise", unit: "scaled", category: "frequency_domain" },
  { key: "haystack_score", label: "Haystack Score", unit: "-", category: "frequency_domain" },
  { key: "narrowband_ratio", label: "Narrowband Ratio", unit: "-", category: "frequency_domain" },
  { key: "peak_drift", label: "Peak Drift", unit: "-", category: "frequency_domain" },

  // Envelope — demodulated, where bearing faults surface first.
  { key: "envelope_rms", label: "Envelope RMS", unit: "scaled", category: "envelope" },
  { key: "ftf_band_energy", label: "Cage (FTF) Energy", unit: "-", category: "envelope" },
  { key: "bsf_band_energy", label: "Ball Spin (BSF) Energy", unit: "-", category: "envelope" },
  { key: "bpfo_band_energy", label: "Outer Race (BPFO) Energy", unit: "-", category: "envelope" },
  { key: "bpfi_band_energy", label: "Inner Race (BPFI) Energy", unit: "-", category: "envelope" },
  { key: "bearing_harmonic_energy", label: "Bearing Harmonic Energy", unit: "-", category: "envelope" },
  { key: "envelope_peak", label: "Envelope Peak", unit: "scaled", category: "envelope" },
  { key: "envelope_kurtosis", label: "Envelope Kurtosis", unit: "-", category: "envelope" },
  { key: "demodulated_peak_prominence", label: "Demodulated Peak Prominence", unit: "-", category: "envelope" },
  { key: "repetition_impact_frequency", label: "Impact Repetition Rate", unit: "Hz", category: "envelope" },
  { key: "resonance_band_energy", label: "Resonance Band Energy", unit: "-", category: "envelope" },

  // Noise — the floor every other reading stands on.
  { key: "noise_floor", label: "Noise Floor", unit: "dB", category: "noise" },
] as const;

export const FACTOR_TREND_KEYS = VIBRATION_FEATURE_CATALOG.map((d) => d.key);

export const FEATURE_CATEGORY_ORDER: readonly VibrationFeatureCategory[] = [
  "time_domain",
  "frequency_domain",
  "envelope",
  "noise",
];

export const FEATURE_CATEGORY_LABELS: Record<VibrationFeatureCategory, string> = {
  time_domain: "Time Domain Features",
  frequency_domain: "Frequency Domain Features",
  envelope: "Envelope Features",
  noise: "Noise Features",
};

/**
 * Backend code (and common shorthand) to catalogue key.
 *
 * Mostly one-to-one — the key is the code — but not always: the FFT band
 * carries its band in the code, and a label does not always normalise to its
 * key ("Standard Deviation" is stored as `std_dev`). Generated alongside the
 * catalogue so a new feature cannot arrive without a way to resolve it.
 */
const FEATURE_KEY_ALIASES: Record<string, VibrationFeatureKey> = {
  rms: "rms",
  peak: "peak",
  crest_factor: "crest_factor",
  crestfactor: "crest_factor",
  crest: "crest_factor",
  kurtosis: "kurtosis",
  peak_to_peak: "peak_to_peak",
  peaktopeak: "peak_to_peak",
  std_dev: "std_dev",
  stddev: "std_dev",
  skewness: "skewness",
  impulse_factor: "impulse_factor",
  impulsefactor: "impulse_factor",
  shape_factor: "shape_factor",
  shapefactor: "shape_factor",
  clearance_factor: "clearance_factor",
  clearancefactor: "clearance_factor",
  burst_count: "burst_count",
  burstcount: "burst_count",
  shock_index: "shock_index",
  shockindex: "shock_index",
  modulation_index: "modulation_index",
  modulationindex: "modulation_index",
  rms_change_short: "rms_change_short",
  rmschangeshort: "rms_change_short",
  rms_change_long: "rms_change_long",
  rmschangelong: "rms_change_long",
  zero_crossing_rate: "zero_crossing_rate",
  zerocrossingrate: "zero_crossing_rate",
  dc_offset: "dc_offset",
  dcoffset: "dc_offset",
  fft_band_energy: "fft_band_energy",
  fftbandenergy: "fft_band_energy",
  fft_band_energy_0_500: "fft_band_energy",
  amplitude_1x: "amplitude_1x",
  amplitude1x: "amplitude_1x",
  "1x": "amplitude_1x",
  "1x_amplitude": "amplitude_1x",
  amplitude_2x: "amplitude_2x",
  amplitude2x: "amplitude_2x",
  "2x": "amplitude_2x",
  "2x_amplitude": "amplitude_2x",
  amplitude_3x: "amplitude_3x",
  amplitude3x: "amplitude_3x",
  "3x": "amplitude_3x",
  "3x_amplitude": "amplitude_3x",
  dominant_frequency: "dominant_frequency",
  dominantfrequency: "dominant_frequency",
  dominant_prominence: "dominant_prominence",
  dominantprominence: "dominant_prominence",
  harmonic_count: "harmonic_count",
  harmoniccount: "harmonic_count",
  harmonic_energy_ratio: "harmonic_energy_ratio",
  harmonicenergyratio: "harmonic_energy_ratio",
  sideband_spacing: "sideband_spacing",
  sidebandspacing: "sideband_spacing",
  sideband_energy_ratio: "sideband_energy_ratio",
  sidebandenergyratio: "sideband_energy_ratio",
  spectral_centroid: "spectral_centroid",
  spectralcentroid: "spectral_centroid",
  spectral_spread: "spectral_spread",
  spectralspread: "spectral_spread",
  spectral_entropy: "spectral_entropy",
  spectralentropy: "spectral_entropy",
  broadband_noise: "broadband_noise",
  broadbandnoise: "broadband_noise",
  haystack_score: "haystack_score",
  haystackscore: "haystack_score",
  narrowband_ratio: "narrowband_ratio",
  narrowbandratio: "narrowband_ratio",
  peak_drift: "peak_drift",
  peakdrift: "peak_drift",
  envelope_rms: "envelope_rms",
  enveloperms: "envelope_rms",
  ftf_band_energy: "ftf_band_energy",
  ftfbandenergy: "ftf_band_energy",
  bsf_band_energy: "bsf_band_energy",
  bsfbandenergy: "bsf_band_energy",
  bpfo_band_energy: "bpfo_band_energy",
  bpfobandenergy: "bpfo_band_energy",
  bpfi_band_energy: "bpfi_band_energy",
  bpfibandenergy: "bpfi_band_energy",
  bearing_harmonic_energy: "bearing_harmonic_energy",
  bearingharmonicenergy: "bearing_harmonic_energy",
  envelope_peak: "envelope_peak",
  envelopepeak: "envelope_peak",
  envelope_kurtosis: "envelope_kurtosis",
  envelopekurtosis: "envelope_kurtosis",
  demodulated_peak_prominence: "demodulated_peak_prominence",
  demodulatedpeakprominence: "demodulated_peak_prominence",
  repetition_impact_frequency: "repetition_impact_frequency",
  repetitionimpactfrequency: "repetition_impact_frequency",
  resonance_band_energy: "resonance_band_energy",
  resonancebandenergy: "resonance_band_energy",
  noise_floor: "noise_floor",
  noisefloor: "noise_floor",
};

function normalizeToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function resolveVibrationFeatureKey(
  raw: string | undefined | null
): VibrationFeatureKey | null {
  if (!raw) return null;
  const token = normalizeToken(raw);
  // Own properties only. A bare `FEATURE_KEY_ALIASES[token]` also searches
  // Object.prototype, where "constructor" is a truthy value that is not a
  // feature key — and callers treat anything non-null as one.
  if (Object.prototype.hasOwnProperty.call(FEATURE_KEY_ALIASES, token)) {
    return FEATURE_KEY_ALIASES[token];
  }

  for (const def of VIBRATION_FEATURE_CATALOG) {
    if (normalizeToken(def.label) === token) return def.key;
  }
  return null;
}

export function getFeatureDefinition(
  key: VibrationFeatureKey
): VibrationFeatureDefinition {
  return VIBRATION_FEATURE_CATALOG.find((def) => def.key === key)!;
}

export function formatFeatureUnit(unit: string | undefined): string {
  if (!unit || unit === "-") return "—";
  return unit;
}
