import React, { useCallback, useMemo } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { useVibrationSettings } from "@/hooks/useVibrationSettings";
import { getDeviceMaxChannelCount } from "@/lib/vibration-settings-utils";
import { DeviceInfoCard } from "./DeviceInfoCard";
import { ChannelConfigurationSection } from "./ChannelConfigurationSection";
import { ChannelMappingOverview } from "./ChannelMappingOverview";
import { ThresholdRulesSection } from "./ThresholdRulesSection";
import { ThresholdCoverageMatrix } from "./ThresholdCoverageMatrix";
import { SettingsPageActions } from "./SettingsPageActions";
import { analysisPageStack } from "@/components/analysis/analysis-layout";
import { PageSection } from "@/components/layout/PageSection";
import { useThresholdRules } from "@/hooks/useThresholdRules";
import { buildFeatureCodeMap, rulesToThresholdConfigs } from "@/lib/threshold-rule-adapters";

export function VibrationSettingsModule() {
  const { showToast } = useToast();
  const {
    draft,
    loading,
    error,
    isDirty,
    editingChannels,
    updateChannel,
    resetChannelRow,
    toggleChannelEdit,
    addChannelRow,
    removeChannelRow,
    save,
    cancel,
    resetAll,
  } = useVibrationSettings();

  // Threshold rules save independently through the API (see ThresholdRulesSection);
  // only channel/device edits go through the draft's own Save action.
  const { rules, resolveFor } = useThresholdRules();
  const coverageThresholds = useMemo(() => {
    const codeByKey = buildFeatureCodeMap(rules);
    return rulesToThresholdConfigs(resolveFor, codeByKey);
  }, [rules, resolveFor]);

  const handleSave = useCallback(() => {
    save();
    showToast("Vibration settings saved successfully.", "success");
  }, [save, showToast]);

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

        <ThresholdRulesSection />

        <ThresholdCoverageMatrix thresholds={coverageThresholds} />

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
