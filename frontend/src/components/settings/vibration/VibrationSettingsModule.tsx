import React, { useCallback } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { useVibrationSettings } from "@/hooks/useVibrationSettings";
import { getDeviceMaxChannelCount, isThresholdValid } from "@/lib/vibration-settings-utils";
import { DeviceInfoCard } from "./DeviceInfoCard";
import { ChannelConfigurationSection } from "./ChannelConfigurationSection";
import { ChannelMappingOverview } from "./ChannelMappingOverview";
import { ThresholdConfigurationSection } from "./ThresholdConfigurationSection";
import { ThresholdCoverageMatrix } from "./ThresholdCoverageMatrix";
import { SettingsPageActions } from "./SettingsPageActions";
import { analysisPageStack } from "@/components/analysis/analysis-layout";
import { PageSection } from "@/components/layout/PageSection";

export function VibrationSettingsModule() {
  const { showToast } = useToast();
  const {
    draft,
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
  } = useVibrationSettings();

  const handleSave = useCallback(() => {
    const invalidRows = draft.thresholds.filter((row) => row.enabled && !isThresholdValid(row));
    if (invalidRows.length > 0) {
      showToast(
        "Fix threshold rows where danger must be greater than warning before saving.",
        "error"
      );
      return;
    }
    save();
    showToast("Vibration settings saved successfully.", "success");
  }, [draft.thresholds, save, showToast]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-g6 rounded-xl border border-border bg-white">
        <div className="flex items-center gap-g2 text-muted-foreground">
          <Loader2 size={22} className="animate-spin text-brand" />
          <span className="text-sm font-medium">Loading vibration settings…</span>
        </div>
      </div>
    );
  }

  return (
    <PageSection
      title="Vibration Settings"
      description="Configure device acquisition settings, channel mapping, and alarm thresholds for vibration monitoring."
    >
      <div className={analysisPageStack}>
        {error && (
          <div className="flex items-start gap-g2 rounded-lg border border-destructive/25 bg-destructive/5 px-g3 py-g2 text-sm text-destructive">
            <AlertCircle size={18} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <DeviceInfoCard device={draft.device} />

        <ChannelConfigurationSection
          channels={draft.channels}
          maxChannelCount={getDeviceMaxChannelCount(draft.device)}
          editingChannels={editingChannels}
          onUpdate={updateChannel}
          onResetRow={resetChannelRow}
          onToggleEdit={toggleChannelEdit}
          onAddRow={addChannelRow}
          onRemoveRow={removeChannelRow}
        />

        <ChannelMappingOverview channels={draft.channels} />

        <ThresholdConfigurationSection
          thresholds={draft.thresholds}
          editingThresholds={editingThresholds}
          onUpdate={updateThreshold}
          onResetRow={resetThresholdRow}
          onToggleEdit={toggleThresholdEdit}
        />

        <ThresholdCoverageMatrix thresholds={draft.thresholds} />

        <SettingsPageActions
          isDirty={isDirty}
          onSave={handleSave}
          onReset={resetAll}
          onCancel={cancel}
        />
      </div>
    </PageSection>
  );
}
