import React from "react";
import { AlertTriangle, Gauge, Pencil, RotateCcw } from "lucide-react";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { Button } from "@/components/ui/Button";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import {
  channelLabel,
  formatThresholdParameterLabel,
  isThresholdValid,
} from "@/lib/vibration-settings-utils";
import { type ThresholdConfig } from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

interface ThresholdConfigurationSectionProps {
  thresholds: ThresholdConfig[];
  editingThresholds: Set<string>;
  onUpdate: (
    channelNo: number,
    parameter: ThresholdConfig["parameter"],
    patch: Partial<ThresholdConfig>
  ) => void;
  onResetRow: (channelNo: number, parameter: ThresholdConfig["parameter"]) => void;
  onToggleEdit: (key: string) => void;
}

function rowKey(channelNo: number, parameter: string): string {
  return `${channelNo}-${parameter}`;
}

export function ThresholdConfigurationSection({
  thresholds,
  editingThresholds,
  onUpdate,
  onResetRow,
  onToggleEdit,
}: ThresholdConfigurationSectionProps) {
  return (
    <SettingsSectionCard
      title="Threshold Configuration"
      description="Configure warning and danger limits for each channel and parameter."
      icon={<Gauge size={22} strokeWidth={2} />}
      bodyClassName="p-0 sm:p-0"
    >
      <div className="overflow-x-auto max-h-[560px] overflow-y-auto rounded-b-xl">
        <table className="w-full min-w-[920px] text-sm">
          <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur-sm border-b border-border">
            <tr className="text-left">
              <th className="px-4 py-3 font-semibold text-muted-foreground">Channel</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Parameter</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Warning Threshold</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Danger Threshold</th>
              <th className="px-3 py-3 font-semibold text-muted-foreground">Enabled</th>
              <th className="px-4 py-3 font-semibold text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {thresholds.map((row) => {
              const key = rowKey(row.channelNo, row.parameter);
              const isEditing = editingThresholds.has(key);
              const disabled = !isEditing;
              const valid = isThresholdValid(row);
              const showValidationError =
                row.enabled &&
                !valid &&
                (row.warningThreshold != null || row.dangerThreshold != null);

              return (
                <tr
                  key={key}
                  className={cn(
                    "border-b border-border last:border-b-0 transition-colors hover:bg-warm/60",
                    isEditing && "bg-signal-light/5",
                    showValidationError && "bg-destructive/[0.03]"
                  )}
                >
                  <td className="px-4 py-2.5 font-bold text-brand whitespace-nowrap">
                    {channelLabel(row.channelNo)}
                  </td>
                  <td className="px-3 py-2.5 font-medium text-foreground whitespace-nowrap">
                    {formatThresholdParameterLabel(row.parameter)}
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      type="number"
                      step="any"
                      className={cn(
                        analysisSelectClass,
                        "w-28 text-sm py-1.5",
                        showValidationError && "border-destructive/40"
                      )}
                      value={row.warningThreshold ?? ""}
                      disabled={disabled}
                      placeholder="—"
                      onChange={(event) => {
                        const raw = event.target.value;
                        onUpdate(row.channelNo, row.parameter, {
                          warningThreshold: raw === "" ? null : Number(raw),
                        });
                      }}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-col gap-1">
                      <input
                        type="number"
                        step="any"
                        className={cn(
                          analysisSelectClass,
                          "w-28 text-sm py-1.5",
                          showValidationError && "border-destructive/40"
                        )}
                        value={row.dangerThreshold ?? ""}
                        disabled={disabled}
                        placeholder="—"
                        onChange={(event) => {
                          const raw = event.target.value;
                          onUpdate(row.channelNo, row.parameter, {
                            dangerThreshold: raw === "" ? null : Number(raw),
                          });
                        }}
                      />
                      {showValidationError && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-destructive font-medium">
                          <AlertTriangle size={12} />
                          Danger must exceed warning
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <ToggleSwitch
                      id={`threshold-enabled-${key}`}
                      checked={row.enabled}
                      disabled={disabled}
                      onChange={(enabled) => onUpdate(row.channelNo, row.parameter, { enabled })}
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <Button
                        type="button"
                        variant={isEditing ? "primary" : "secondary"}
                        size="sm"
                        icon={<Pencil size={14} />}
                        onClick={() => onToggleEdit(key)}
                      >
                        {isEditing ? "Done" : "Edit"}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        icon={<RotateCcw size={14} />}
                        onClick={() => onResetRow(row.channelNo, row.parameter)}
                      >
                        Reset
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </SettingsSectionCard>
  );
}
