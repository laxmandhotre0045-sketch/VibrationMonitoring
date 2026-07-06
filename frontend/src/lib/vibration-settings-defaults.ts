import {
  THRESHOLD_PARAMETERS,
  VIBRATION_CHANNEL_COUNT,
  type ChannelConfig,
  type ThresholdConfig,
  type VibrationDeviceInfo,
  type VibrationSettingsState,
} from "@/types/vibration-settings";

export const DEFAULT_DEVICE: VibrationDeviceInfo = {
  deviceId: "08:F9:E0:AD:FB:34",
  deviceLabel: "08:F9:E0:AD:FB:34 · 2W Charging",
  mode: "MEMS",
  maxChannelCount: VIBRATION_CHANNEL_COUNT,
};

const CHANNEL_SEEDS: Partial<ChannelConfig>[] = [
  {
    axis: "vertical",
    dataType: "vibration",
    engineeringUnit: "g",
    measurementPointName: "MDE",
    active: true,
  },
  {
    axis: "horizontal",
    dataType: "vibration",
    engineeringUnit: "g",
    measurementPointName: "DE",
    active: true,
  },
  {
    axis: "axial",
    dataType: "vibration",
    engineeringUnit: "g",
    measurementPointName: "NDE",
    active: true,
  },
  {
    axis: "vertical",
    dataType: "vibration",
    engineeringUnit: "g",
    measurementPointName: "Motor Drive End",
    active: true,
  },
  {
    axis: "horizontal",
    dataType: "temperature",
    engineeringUnit: "°C",
    measurementPointName: "Pump Housing",
    active: true,
  },
  {
    axis: "",
    dataType: "vibration",
    engineeringUnit: "",
    measurementPointName: "",
    active: false,
  },
  {
    axis: "",
    dataType: "",
    engineeringUnit: "",
    measurementPointName: "",
    active: false,
  },
  {
    axis: "",
    dataType: "",
    engineeringUnit: "",
    measurementPointName: "",
    active: false,
  },
];

const THRESHOLD_SEEDS: Partial<
  Record<number, Partial<Record<string, { warning: number; danger: number; enabled: boolean }>>>
> = {
  1: {
    rms: { warning: 0.02, danger: 0.05, enabled: true },
    peak: { warning: 0.1, danger: 0.2, enabled: true },
    crest_factor: { warning: 3.5, danger: 5.0, enabled: true },
    kurtosis: { warning: 3.5, danger: 5.0, enabled: false },
  },
  2: {
    rms: { warning: 0.02, danger: 0.05, enabled: true },
    peak: { warning: 0.1, danger: 0.2, enabled: false },
    fft_band_energy: { warning: 0.4, danger: 0.7, enabled: true },
    amplitude_1x: { warning: 0.15, danger: 0.3, enabled: true },
  },
  3: {
    rms: { warning: 0.015, danger: 0.04, enabled: true },
    amplitude_2x: { warning: 0.08, danger: 0.16, enabled: true },
    envelope_rms: { warning: 0.05, danger: 0.12, enabled: true },
  },
  4: {
    rms: { warning: 0.02, danger: 0.05, enabled: true },
    noise_floor: { warning: -55, danger: -45, enabled: true },
  },
};

export function createDefaultChannels(): ChannelConfig[] {
  return Array.from({ length: VIBRATION_CHANNEL_COUNT }, (_, index) => {
    const channelNo = index + 1;
    const seed = CHANNEL_SEEDS[index] ?? {};
    return {
      channelNo,
      axis: seed.axis ?? "",
      dataType: seed.dataType ?? "",
      engineeringUnit: seed.engineeringUnit ?? "",
      measurementPointName: seed.measurementPointName ?? "",
      active: seed.active ?? false,
    };
  });
}

export function createDefaultThresholds(): ThresholdConfig[] {
  const rows: ThresholdConfig[] = [];
  for (let channelNo = 1; channelNo <= VIBRATION_CHANNEL_COUNT; channelNo += 1) {
    for (const param of THRESHOLD_PARAMETERS) {
      const seed = THRESHOLD_SEEDS[channelNo]?.[param.id];
      rows.push({
        channelNo,
        parameter: param.id,
        warningThreshold: seed?.warning ?? null,
        dangerThreshold: seed?.danger ?? null,
        enabled: seed?.enabled ?? false,
      });
    }
  }
  return rows;
}

export function createDefaultVibrationSettings(): VibrationSettingsState {
  return {
    device: DEFAULT_DEVICE,
    channels: createDefaultChannels(),
    thresholds: createDefaultThresholds(),
  };
}
