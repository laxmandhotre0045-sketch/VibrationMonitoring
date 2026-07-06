import { useCallback, useEffect, useMemo, useState } from "react";
import { createDefaultVibrationSettings } from "@/lib/vibration-settings-defaults";
import {
  createEmptyChannel,
  getDeviceMaxChannelCount,
  renumberChannels,
  settingsStatesEqual,
} from "@/lib/vibration-settings-utils";
import { THRESHOLD_PARAMETERS, VIBRATION_CHANNEL_COUNT } from "@/types/vibration-settings";
import type {
  ChannelConfig,
  ThresholdConfig,
  VibrationSettingsState,
} from "@/types/vibration-settings";

const STORAGE_KEY = "sensovibe-vibration-settings";

function loadFromStorage(): VibrationSettingsState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as VibrationSettingsState;
  } catch {
    return null;
  }
}

function persistToStorage(state: VibrationSettingsState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

/**
 * Rebuild thresholds against the current parameter catalog (sourced from the
 * Status section) so persisted settings using an older parameter set stay valid.
 * Values for parameters that still exist are preserved.
 */
function migrateThresholds(
  existing: ThresholdConfig[],
  channelCount: number
): ThresholdConfig[] {
  const rows: ThresholdConfig[] = [];
  for (let channelNo = 1; channelNo <= channelCount; channelNo += 1) {
    for (const param of THRESHOLD_PARAMETERS) {
      const previous = existing.find(
        (row) => row.channelNo === channelNo && row.parameter === param.id
      );
      rows.push(
        previous ?? {
          channelNo,
          parameter: param.id,
          warningThreshold: null,
          dangerThreshold: null,
          enabled: false,
        }
      );
    }
  }
  return rows;
}

function migrateSettings(state: VibrationSettingsState): VibrationSettingsState {
  const maxChannelCount = getDeviceMaxChannelCount(state.device, VIBRATION_CHANNEL_COUNT);
  const channels =
    state.channels.length > 0
      ? renumberChannels(state.channels)
      : createDefaultVibrationSettings().channels;
  const boundedChannels = channels.slice(0, maxChannelCount);

  return {
    ...state,
    device: {
      ...state.device,
      maxChannelCount,
    },
    channels: boundedChannels,
    thresholds: migrateThresholds(state.thresholds ?? [], maxChannelCount),
  };
}

export function useVibrationSettings() {
  const [saved, setSaved] = useState<VibrationSettingsState>(createDefaultVibrationSettings);
  const [draft, setDraft] = useState<VibrationSettingsState>(createDefaultVibrationSettings);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingChannels, setEditingChannels] = useState<Set<number>>(() => new Set());
  const [editingThresholds, setEditingThresholds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const stored = loadFromStorage();
        const initial = migrateSettings(stored ?? createDefaultVibrationSettings());
        setSaved(initial);
        setDraft(initial);
        setError(stored ? null : null);
      } catch {
        setError("Unable to load saved vibration settings. Showing defaults.");
        const defaults = createDefaultVibrationSettings();
        setSaved(defaults);
        setDraft(defaults);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, []);

  const isDirty = useMemo(() => !settingsStatesEqual(draft, saved), [draft, saved]);

  const updateChannel = useCallback((channelNo: number, patch: Partial<ChannelConfig>) => {
    setDraft((prev) => ({
      ...prev,
      channels: prev.channels.map((channel) =>
        channel.channelNo === channelNo ? { ...channel, ...patch } : channel
      ),
    }));
  }, []);

  const updateThreshold = useCallback(
    (channelNo: number, parameter: ThresholdConfig["parameter"], patch: Partial<ThresholdConfig>) => {
      setDraft((prev) => ({
        ...prev,
        thresholds: prev.thresholds.map((row) =>
          row.channelNo === channelNo && row.parameter === parameter ? { ...row, ...patch } : row
        ),
      }));
    },
    []
  );

  const resetChannelRow = useCallback(
    (channelNo: number) => {
      const savedChannel = saved.channels.find((channel) => channel.channelNo === channelNo);
      if (!savedChannel) return;
      setDraft((prev) => ({
        ...prev,
        channels: prev.channels.map((channel) =>
          channel.channelNo === channelNo ? { ...savedChannel } : channel
        ),
      }));
      setEditingChannels((prev) => {
        const next = new Set(prev);
        next.delete(channelNo);
        return next;
      });
    },
    [saved.channels]
  );

  const resetThresholdRow = useCallback(
    (channelNo: number, parameter: ThresholdConfig["parameter"]) => {
      const savedRow = saved.thresholds.find(
        (row) => row.channelNo === channelNo && row.parameter === parameter
      );
      if (!savedRow) return;
      setDraft((prev) => ({
        ...prev,
        thresholds: prev.thresholds.map((row) =>
          row.channelNo === channelNo && row.parameter === parameter ? { ...savedRow } : row
        ),
      }));
      setEditingThresholds((prev) => {
        const next = new Set(prev);
        next.delete(`${channelNo}-${parameter}`);
        return next;
      });
    },
    [saved.thresholds]
  );

  const toggleChannelEdit = useCallback((channelNo: number) => {
    setEditingChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channelNo)) next.delete(channelNo);
      else next.add(channelNo);
      return next;
    });
  }, []);

  const addChannelRow = useCallback(() => {
    setDraft((prev) => {
      const maxChannelCount = getDeviceMaxChannelCount(prev.device, VIBRATION_CHANNEL_COUNT);
      if (prev.channels.length >= maxChannelCount) return prev;

      const nextChannelNo = prev.channels.length + 1;
      const nextChannels = [...prev.channels, createEmptyChannel(nextChannelNo)];

      setEditingChannels((editing) => {
        const next = new Set(editing);
        next.add(nextChannelNo);
        return next;
      });

      return { ...prev, channels: nextChannels };
    });
  }, []);

  const removeChannelRow = useCallback((channelNo: number) => {
    setDraft((prev) => {
      if (prev.channels.length === 0) return prev;

      const nextChannels = renumberChannels(
        prev.channels.filter((channel) => channel.channelNo !== channelNo)
      );

      setEditingChannels(new Set());

      return { ...prev, channels: nextChannels };
    });
  }, []);

  const toggleThresholdEdit = useCallback((key: string) => {
    setEditingThresholds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const save = useCallback(() => {
    setSaved(draft);
    persistToStorage(draft);
    setEditingChannels(new Set());
    setEditingThresholds(new Set());
    return true;
  }, [draft]);

  const cancel = useCallback(() => {
    setDraft(saved);
    setEditingChannels(new Set());
    setEditingThresholds(new Set());
  }, [saved]);

  const resetAll = useCallback(() => {
    setDraft(saved);
    setEditingChannels(new Set());
    setEditingThresholds(new Set());
  }, [saved]);

  return {
    draft,
    saved,
    loading,
    error,
    isDirty,
    editingChannels,
    editingThresholds,
    updateChannel,
    updateThreshold,
    resetChannelRow,
    resetThresholdRow,
    toggleChannelEdit,
    addChannelRow,
    removeChannelRow,
    toggleThresholdEdit,
    save,
    cancel,
    resetAll,
  };
}
