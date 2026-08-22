import React from "react";
import { Bookmark, SlidersHorizontal } from "lucide-react";
import type { Baseline } from "@/types/baseline";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisBodyStack,
  analysisCardPad,
  analysisGridGap,
  analysisInputClass,
  analysisSelectClass,
} from "@/components/analysis/analysis-layout";
import { FormField, TextInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

type PlotSource = "upload" | "baseline";

interface PrimaryBaseline {
  name: string;
  created_at: string;
  sample_count: number;
  plot_count: number;
}

interface BaselineSelectionPanelProps {
  sensorId: string;
  primaryBaseline: PrimaryBaseline | null | undefined;
  baselineList: { items: Baseline[]; total: number } | undefined;
  showAllBaselines: boolean;
  onToggleAllBaselines: () => void;
  plotSource: PlotSource;
  onPlotSourceChange: (source: PlotSource) => void;
  selectedBaselineId: string;
  onBaselineIdChange: (id: string) => void;
  channelCount: number;
  onChannelCountChange: (count: number) => void;
  onActiveChannelClamp: (maxChannel: number) => void;
  formatDateTime: (iso: string) => string;
}

const innerBlockClass =
  "rounded-md border border-border border-l-2 border-l-signal-light bg-white px-3 py-2.5";

export function BaselineSelectionPanel({
  sensorId,
  primaryBaseline,
  baselineList,
  showAllBaselines,
  onToggleAllBaselines,
  plotSource,
  onPlotSourceChange,
  selectedBaselineId,
  onBaselineIdChange,
  channelCount,
  onChannelCountChange,
  onActiveChannelClamp,
  formatDateTime,
}: BaselineSelectionPanelProps) {
  if (!sensorId) return null;

  return (
    <GlassCard className={analysisCardPad} delay={0.06}>
      <AnalysisSectionHeader
        icon={Bookmark}
        title="Baseline & Channel Configuration"
        subtitle="Primary baseline, comparison source, and channel setup for health monitoring (CH-1 through CH-8)."
      />

      <div className={analysisBodyStack}>
        <div className={cn("grid grid-cols-1 lg:grid-cols-2", analysisGridGap)}>
          <div className={cn(innerBlockClass, "space-y-g1")}>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Primary Baseline
            </p>
            {primaryBaseline ? (
              <p className="text-sm text-foreground leading-snug">
                <span className="font-semibold">{primaryBaseline.name}</span>
                {" · "}
                {formatDateTime(primaryBaseline.created_at)}
                {" · "}
                {primaryBaseline.sample_count} samples
                {primaryBaseline.plot_count > 0 && (
                  <> · {primaryBaseline.plot_count} plots stored</>
                )}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No primary baseline set for this sensor.
              </p>
            )}
            {baselineList && baselineList.total > 0 && (
              <button
                type="button"
                className="text-sm font-medium text-signal-dark hover:underline"
                onClick={onToggleAllBaselines}
              >
                {showAllBaselines ? "Hide" : "View"} all baselines ({baselineList.total})
              </button>
            )}
            {showAllBaselines && baselineList && baselineList.items.length > 0 && (
              <ul className="mt-g1 max-h-28 overflow-y-auto space-y-g1 text-sm text-muted-foreground">
                {baselineList.items.map((b) => (
                  <li key={b.id} className="flex items-center gap-2">
                    {b.is_primary && (
                      <span className="text-sm font-semibold text-signal-dark uppercase">
                        Primary
                      </span>
                    )}
                    <span>{b.name}</span>
                    <span>· {formatDateTime(b.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={innerBlockClass}>
            <FormField label="Channel Count (8 Channels)" compact>
              <div className="flex items-center gap-2">
                <SlidersHorizontal
                  size={22}
                  className="shrink-0 text-signal-dark"
                  aria-hidden
                />
                <TextInput
                  type="number"
                  min={1}
                  max={32}
                  className={cn(analysisInputClass, "flex-1")}
                  value={channelCount}
                  onChange={(e) => {
                    const count = Number(e.target.value);
                    onChannelCountChange(count);
                    onActiveChannelClamp(Math.max(0, count - 1));
                  }}
                />
              </div>
            </FormField>
            <p className="mt-g1 text-xs text-muted-foreground">
              Supports up to 8 vibration channels for Status (Health) monitoring.
            </p>
          </div>
        </div>

        {baselineList && baselineList.total > 0 && (
          <div className={cn(innerBlockClass, "space-y-g2")}>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Comparison Source
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className={cn(analysisSelectClass, "w-auto min-w-[130px]")}
                value={plotSource}
                onChange={(e) => onPlotSourceChange(e.target.value as PlotSource)}
              >
                <option value="upload">Timeline capture</option>
                <option value="baseline">Saved baseline</option>
              </select>
              {plotSource === "baseline" && (
                <select
                  className={cn(analysisSelectClass, "w-auto min-w-[160px]")}
                  value={selectedBaselineId}
                  onChange={(e) => onBaselineIdChange(e.target.value)}
                >
                  <option value="">Select baseline...</option>
                  {baselineList.items.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                      {b.is_primary ? " (primary)" : ""}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
        )}
      </div>
    </GlassCard>
  );
}
