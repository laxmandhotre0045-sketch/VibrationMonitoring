import type {
  ChannelConfig,
  ChannelReadinessStatus,
  ThresholdConfig,
  ThresholdCoverageStatus,
  VibrationSettingsState,
} from "@/types/vibration-settings";

export function channelLabel(channelNo: number): string {
  return `CH-${channelNo}`;
}

export function isChannelFullyConfigured(channel: ChannelConfig): boolean {
  return Boolean(
    channel.axis &&
      channel.dataType &&
      channel.engineeringUnit &&
      channel.measurementPointName.trim()
  );
}

export function isChannelPartiallyConfigured(channel: ChannelConfig): boolean {
  if (isChannelFullyConfigured(channel)) return false;
  return Boolean(
    channel.axis ||
      channel.dataType ||
      channel.engineeringUnit ||
      channel.measurementPointName.trim()
  );
}

export function getChannelReadinessStatus(channel: ChannelConfig): ChannelReadinessStatus {
  if (isChannelFullyConfigured(channel)) return "configured";
  if (isChannelPartiallyConfigured(channel)) return "partial";
  return "empty";
}

export function isThresholdValid(row: ThresholdConfig): boolean {
  if (!row.enabled) return true;
  if (row.warningThreshold == null || row.dangerThreshold == null) return false;
  return row.dangerThreshold > row.warningThreshold;
}

export function getThresholdCoverageStatus(row: ThresholdConfig): ThresholdCoverageStatus {
  const hasValues = row.warningThreshold != null || row.dangerThreshold != null;

  if (!row.enabled) {
    return hasValues ? "disabled" : "empty";
  }

  if (
    row.warningThreshold != null &&
    row.dangerThreshold != null &&
    row.dangerThreshold > row.warningThreshold
  ) {
    return "saved";
  }

  return "incomplete";
}

export function settingsStatesEqual(a: VibrationSettingsState, b: VibrationSettingsState): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function findThresholdRow(
  thresholds: ThresholdConfig[],
  channelNo: number,
  parameter: ThresholdConfig["parameter"]
): ThresholdConfig | undefined {
  return thresholds.find((row) => row.channelNo === channelNo && row.parameter === parameter);
}

export function createEmptyChannel(channelNo: number): ChannelConfig {
  return {
    channelNo,
    axis: "",
    dataType: "",
    engineeringUnit: "",
    measurementPointName: "",
    active: false,
  };
}

/** Reassign sequential channel numbers after add/remove. */
export function renumberChannels(channels: ChannelConfig[]): ChannelConfig[] {
  return channels.map((channel, index) => ({
    ...channel,
    channelNo: index + 1,
  }));
}

export function getDeviceMaxChannelCount(
  device: VibrationSettingsState["device"],
  fallback = 8
): number {
  return device.maxChannelCount > 0 ? device.maxChannelCount : fallback;
}

export function canAddChannelRow(
  channels: ChannelConfig[],
  maxChannelCount: number
): boolean {
  return channels.length < maxChannelCount;
}

export function canRemoveChannelRow(channels: ChannelConfig[]): boolean {
  return channels.length > 0;
}
