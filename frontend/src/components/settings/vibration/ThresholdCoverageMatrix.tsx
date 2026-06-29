import React from "react";
import { Grid3X3 } from "lucide-react";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import {
  channelLabel,
  findThresholdRow,
  getThresholdCoverageStatus,
} from "@/lib/vibration-settings-utils";
import {
  THRESHOLD_PARAMETERS,
  VIBRATION_CHANNEL_COUNT,
  type ThresholdConfig,
  type ThresholdCoverageStatus,
} from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

const COVERAGE_STYLES: Record<
  ThresholdCoverageStatus,
  { cell: string; dot: string; label: string }
> = {
  saved: {
    cell: "bg-machine-healthy/12 border-machine-healthy/25 hover:bg-machine-healthy/18",
    dot: "bg-machine-healthy",
    label: "Saved",
  },
  incomplete: {
    cell: "bg-signal-light/15 border-signal-light/35 hover:bg-signal-light/22",
    dot: "bg-signal-light",
    label: "Incomplete",
  },
  disabled: {
    cell: "bg-brand/[0.06] border-brand/15 hover:bg-brand/[0.1]",
    dot: "bg-brand",
    label: "Disabled",
  },
  empty: {
    cell: "bg-muted/30 border-border hover:bg-muted/45",
    dot: "bg-muted-foreground/35",
    label: "Not Configured",
  },
};

interface ThresholdCoverageMatrixProps {
  thresholds: ThresholdConfig[];
}

export function ThresholdCoverageMatrix({ thresholds }: ThresholdCoverageMatrixProps) {
  const channels = Array.from({ length: VIBRATION_CHANNEL_COUNT }, (_, i) => i + 1);

  return (
    <SettingsSectionCard
      title="Threshold Coverage"
      description="Matrix view of threshold configuration status across all channels and parameters."
      icon={<Grid3X3 size={22} strokeWidth={2} />}
    >
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
        {(Object.keys(COVERAGE_STYLES) as ThresholdCoverageStatus[]).map((status) => (
          <span key={status} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2 w-2 rounded-full", COVERAGE_STYLES[status].dot)} />
            {COVERAGE_STYLES[status].label}
          </span>
        ))}
      </div>

      <div className="overflow-x-auto rounded-md border border-border border-l-2 border-l-signal-light">
        <table className="w-full min-w-[880px] text-xs">
          <thead>
            <tr className="border-b border-border bg-surface/60">
              <th className="sticky left-0 z-10 bg-surface/95 px-3 py-2.5 text-left font-semibold text-muted-foreground border-r border-border">
                Channel
              </th>
              {THRESHOLD_PARAMETERS.map((param) => (
                <th
                  key={param.id}
                  className="px-2 py-2.5 text-center font-semibold text-muted-foreground whitespace-nowrap"
                >
                  {param.unit ? `${param.label} (${param.unit})` : param.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {channels.map((channelNo) => (
              <tr key={channelNo} className="border-b border-border last:border-b-0">
                <td className="sticky left-0 z-10 bg-white px-3 py-2 font-bold text-brand border-r border-border whitespace-nowrap">
                  {channelLabel(channelNo)}
                </td>
                {THRESHOLD_PARAMETERS.map((param) => {
                  const row = findThresholdRow(thresholds, channelNo, param.id);
                  const status = row ? getThresholdCoverageStatus(row) : "empty";
                  const styles = COVERAGE_STYLES[status];

                  return (
                    <td key={param.id} className="px-1.5 py-1.5">
                      <div
                        className={cn(
                          "flex h-9 items-center justify-center rounded-md border transition-colors",
                          styles.cell
                        )}
                        title={`${channelLabel(channelNo)} · ${param.label}: ${styles.label}`}
                      >
                        <span className={cn("h-2.5 w-2.5 rounded-full", styles.dot)} />
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SettingsSectionCard>
  );
}
