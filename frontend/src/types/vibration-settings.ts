export const VIBRATION_CHANNEL_COUNT = 8;

export type ChannelAxis = "vertical" | "horizontal" | "axial";
export type ChannelDataType =
  | "vibration"
  | "temperature"
  | "velocity"
  | "acceleration"
  | "displacement";
export type EngineeringUnit = "g" | "mm/s" | "µm" | "°C";

export type ThresholdParameter =
  | "rms"
  | "vrms"
  | "peak"
  | "saturation"
  | "crest_factor"
  | "skewness"
  | "temperature";

export interface ThresholdParameterMeta {
  id: ThresholdParameter;
  label: string;
  unit: string;
}

export const THRESHOLD_PARAMETERS: ThresholdParameterMeta[] = [
  { id: "rms", label: "RMS", unit: "g" },
  { id: "vrms", label: "VRMS", unit: "mm/s" },
  { id: "peak", label: "Peak", unit: "g" },
  { id: "saturation", label: "Saturation", unit: "" },
  { id: "crest_factor", label: "Crest Factor", unit: "" },
  { id: "skewness", label: "Skewness", unit: "" },
  { id: "temperature", label: "Temperature", unit: "°C" },
];

export interface ChannelConfig {
  channelNo: number;
  axis: ChannelAxis | "";
  dataType: ChannelDataType | "";
  engineeringUnit: EngineeringUnit | "";
  measurementPointName: string;
  active: boolean;
}

export interface ThresholdConfig {
  channelNo: number;
  parameter: ThresholdParameter;
  warningThreshold: number | null;
  dangerThreshold: number | null;
  enabled: boolean;
}

export interface VibrationDeviceInfo {
  deviceId: string;
  deviceLabel: string;
  mode: string;
  /** Maximum channels supported by the device hardware. */
  maxChannelCount: number;
}

export interface VibrationSettingsState {
  device: VibrationDeviceInfo;
  channels: ChannelConfig[];
  thresholds: ThresholdConfig[];
}

export type ChannelReadinessStatus = "configured" | "partial" | "empty";
export type ThresholdCoverageStatus = "saved" | "incomplete" | "disabled" | "empty";

export type SettingsModuleId = "vibration" | "platform";
