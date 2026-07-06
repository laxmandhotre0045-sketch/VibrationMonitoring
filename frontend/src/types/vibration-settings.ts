import {
  VIBRATION_FEATURE_CATALOG,
  type VibrationFeatureCategory,
  type VibrationFeatureKey,
} from "@/lib/vibration-features";

export const VIBRATION_CHANNEL_COUNT = 8;

export type ChannelAxis = "vertical" | "horizontal" | "axial";
export type ChannelDataType =
  | "vibration"
  | "temperature"
  | "velocity"
  | "acceleration"
  | "displacement";
export type EngineeringUnit = "g" | "mm/s" | "µm" | "°C";

/**
 * Threshold parameters mirror the Status (Health) section feature catalog so the
 * Settings page always stays in sync with the parameters analysed there.
 * @see src/lib/vibration-features.ts (VIBRATION_FEATURE_CATALOG)
 */
export type ThresholdParameter = VibrationFeatureKey;

export type ThresholdParameterCategory = VibrationFeatureCategory;

export interface ThresholdParameterMeta {
  id: ThresholdParameter;
  label: string;
  unit: string;
  category: ThresholdParameterCategory;
}

export const THRESHOLD_PARAMETERS: ThresholdParameterMeta[] = VIBRATION_FEATURE_CATALOG.map(
  (feature) => ({
    id: feature.key,
    label: feature.label,
    unit: feature.unit === "-" ? "" : feature.unit,
    category: feature.category,
  })
);

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
