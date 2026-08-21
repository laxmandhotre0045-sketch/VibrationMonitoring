import React from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { FormField } from "@/components/ui/FormField";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import {
  ORBIT_BANDWIDTHS,
  ORBIT_DISPLAY_REVS,
  ORBIT_FILTER_REVS,
  ORBIT_HARMONICS,
} from "@/types/orbit";
import { cn } from "@/lib/utils";

export interface OrthogonalityCheck {
  /** null when the local channel configuration does not describe both channels. */
  isOrthogonal: boolean | null;
  xAxis: string | null;
  yAxis: string | null;
  message: string;
}

interface OrbitControlsProps {
  xChannel: number;
  yChannel: number;
  channelCount: number;
  onXChannelChange: (value: number) => void;
  onYChannelChange: (value: number) => void;
  harmonic: number;
  onHarmonicChange: (value: number) => void;
  bandwidthPercent: number;
  onBandwidthChange: (value: number) => void;
  filterRevolutions: number | "auto";
  onFilterRevolutionsChange: (value: number | "auto") => void;
  displayRevolutions: number;
  onDisplayRevolutionsChange: (value: number) => void;
  showUnfiltered: boolean;
  onShowUnfilteredChange: (value: boolean) => void;
  orthogonality: OrthogonalityCheck;
  disabled?: boolean;
}

export function OrbitControls({
  xChannel,
  yChannel,
  channelCount,
  onXChannelChange,
  onYChannelChange,
  harmonic,
  onHarmonicChange,
  bandwidthPercent,
  onBandwidthChange,
  filterRevolutions,
  onFilterRevolutionsChange,
  displayRevolutions,
  onDisplayRevolutionsChange,
  showUnfiltered,
  onShowUnfilteredChange,
  orthogonality,
  disabled = false,
}: OrbitControlsProps) {
  const channels = Array.from({ length: Math.max(2, channelCount) }, (_, i) => i);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <FormField label="X probe" compact>
          <select
            className={analysisSelectClass}
            value={xChannel}
            onChange={(e) => onXChannelChange(Number(e.target.value))}
            disabled={disabled}
          >
            {channels.map((c) => (
              <option key={c} value={c} disabled={c === yChannel}>
                CH {c + 1} (ch{c})
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Y probe" compact>
          <select
            className={analysisSelectClass}
            value={yChannel}
            onChange={(e) => onYChannelChange(Number(e.target.value))}
            disabled={disabled}
          >
            {channels.map((c) => (
              <option key={c} value={c} disabled={c === xChannel}>
                CH {c + 1} (ch{c})
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Band" compact>
          <select
            className={analysisSelectClass}
            value={harmonic}
            onChange={(e) => onHarmonicChange(Number(e.target.value))}
            disabled={disabled}
          >
            {ORBIT_HARMONICS.map((h) => (
              <option key={h} value={h}>
                {h}× synchronous
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Bandwidth (±%)" compact>
          <select
            className={analysisSelectClass}
            value={bandwidthPercent}
            onChange={(e) => onBandwidthChange(Number(e.target.value))}
            disabled={disabled}
          >
            {ORBIT_BANDWIDTHS.map((b) => (
              <option key={b} value={b}>
                ±{b}%
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Filter over" compact>
          <select
            className={analysisSelectClass}
            value={filterRevolutions}
            onChange={(e) =>
              onFilterRevolutionsChange(
                e.target.value === "auto" ? "auto" : Number(e.target.value)
              )
            }
            disabled={disabled}
          >
            <option value="auto">Auto</option>
            {ORBIT_FILTER_REVS.map((r) => (
              <option key={r} value={r}>
                {r} rev
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Display" compact>
          <select
            className={analysisSelectClass}
            value={displayRevolutions}
            onChange={(e) => onDisplayRevolutionsChange(Number(e.target.value))}
            disabled={disabled}
          >
            {ORBIT_DISPLAY_REVS.map((r) => (
              <option key={r} value={r}>
                {r} rev
              </option>
            ))}
          </select>
        </FormField>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold",
            orthogonality.isOrthogonal === true
              ? "border-machine-healthy/30 bg-machine-healthy/10 text-machine-healthy"
              : "border-signal-light/40 bg-signal-light/10 text-signal-dark"
          )}
        >
          {orthogonality.isOrthogonal === true ? (
            <CheckCircle2 size={13} aria-hidden />
          ) : (
            <AlertTriangle size={13} aria-hidden />
          )}
          {orthogonality.message}
        </span>

        <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <ToggleSwitch
            checked={showUnfiltered}
            onChange={onShowUnfilteredChange}
            disabled={disabled}
          />
          Show unfiltered orbit
        </label>
      </div>
    </div>
  );
}
