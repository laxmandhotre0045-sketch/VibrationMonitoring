/**
 * Acquisition & DAQ configuration — mirrors backend/app/schemas/acquisition.py.
 *
 * The API speaks camelCase for the config payload (it is also consumed by the
 * edge uploader) but snake_case inside `channelMap`, matching how the mapping is
 * stored. Both shapes are reproduced verbatim rather than normalised, so a field
 * name here is searchable in the backend.
 */

export const CHANNEL_AXES = ["VERTICAL", "HORIZONTAL", "AXIAL"] as const;
export type ChannelAxis = (typeof CHANNEL_AXES)[number];

export const CHANNEL_SIGNAL_TYPES = [
  "VIBRATION",
  "TEMPERATURE",
  "PRESSURE",
  "TACHO",
] as const;
export type ChannelSignalType = (typeof CHANNEL_SIGNAL_TYPES)[number];

/** Freshness of stored data — not a broker socket check. */
export interface ChannelMapEntry {
  channel_index: number;
  machine_axis: ChannelAxis;
  signal_type: ChannelSignalType;
  label: string | null;
}

export interface AcquisitionCalculated {
  /** Fs / (2 × LOR). LOR counts lines from DC to Nyquist. */
  frequencyResolutionHz: number;
  blockTimeSeconds: number;
  /** 2 × LOR — what the device must actually capture per block. */
  samplesPerBlock: number;
  totalAcquisitionTimeSeconds: number;
  stepSizeSamples: number;
  nyquistHz: number;
  samplesPerLine: number;
  /** Fmax-based analyser view, for comparison only. Never used for an FFT. */
  linesBelowFmax: number | null;
  fmaxRelativeResolutionHz: number | null;
  fmaxRelativeBlockTimeSeconds: number | null;
}

export interface AcquisitionMappedChannel {
  transducerType: string;
  signalType: string;
  channelIndex: number;
  machineAxis: string;
  label: string | null;
}

export interface AcquisitionConfig {
  sampleRateHz: number;
  ksps: number;
  fmaxHz: number;
  lor: number;
  windowType: string;
  averageCount: number;
  overlapPercentage: number;
  sensitivityMvPerG: number | null;
  sensitivityUnit: string;
  /** Stored sensitivity is below 1 mV/g — a placeholder, not hardware data. */
  sensitivitySuspect: boolean;
  totalChannelCount: number;
  collectionIntervalMinutes: number;
  /** Flat copies of the derived values; identical to the matching "calculated" keys. */
  frequencyResolutionHz: number;
  blockTimeSeconds: number;
  samplesPerBlock: number;
  totalAcquisitionTimeSeconds: number;
  calculated: AcquisitionCalculated;
  sensorId: string;
  platformSensorId: string;
  deviceId: string | null;
  channels: AcquisitionMappedChannel[];
  channelMap: ChannelMapEntry[];
  success: boolean;
}

/** Partial save — omitted fields keep their stored values. */
export interface AcquisitionConfigUpdate {
  sensor_id: string;
  ksps?: number;
  sample_rate_hz?: number;
  fmax_hz?: number;
  lor?: number;
  window_type?: string;
  average_count?: number;
  overlap_percentage?: number;
  total_channel_count?: number;
  collection_interval_minutes?: number;
  sensitivity_mv_per_g?: number;
  channel_map?: Array<{
    channel_index: number;
    machine_axis: ChannelAxis;
    signal_type: ChannelSignalType;
    label?: string | null;
  }>;
}
