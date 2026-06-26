export type VibrationFeatureKey =
  | "rms"
  | "peak"
  | "crest_factor"
  | "kurtosis"
  | "fft_band_energy"
  | "amplitude_1x"
  | "amplitude_2x"
  | "amplitude_3x"
  | "envelope_rms"
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
  { key: "rms", label: "RMS", unit: "scaled", category: "time_domain" },
  { key: "peak", label: "Peak", unit: "scaled", category: "time_domain" },
  { key: "crest_factor", label: "Crest Factor", unit: "-", category: "time_domain" },
  { key: "kurtosis", label: "Kurtosis", unit: "-", category: "time_domain" },
  {
    key: "fft_band_energy",
    label: "FFT Band Energy (0-500 Hz)",
    unit: "scaled²",
    category: "frequency_domain",
  },
  { key: "amplitude_1x", label: "1X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "amplitude_2x", label: "2X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "amplitude_3x", label: "3X Amplitude", unit: "scaled", category: "frequency_domain" },
  { key: "envelope_rms", label: "Envelope RMS", unit: "scaled", category: "envelope" },
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

const FEATURE_KEY_ALIASES: Record<string, VibrationFeatureKey> = {
  rms: "rms",
  peak: "peak",
  crest_factor: "crest_factor",
  crest: "crest_factor",
  crestfactor: "crest_factor",
  kurtosis: "kurtosis",
  fft_band_energy: "fft_band_energy",
  fft_band_energy_0_500: "fft_band_energy",
  fftbandenergy: "fft_band_energy",
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
  envelope_rms: "envelope_rms",
  enveloperms: "envelope_rms",
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
  if (FEATURE_KEY_ALIASES[token]) return FEATURE_KEY_ALIASES[token];

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
