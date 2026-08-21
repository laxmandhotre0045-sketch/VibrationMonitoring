import React from "react";
import { Shuffle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { analysisInputClass, analysisSelectClass } from "@/components/analysis/analysis-layout";
import {
  WATERFALL_MODE_LABELS,
  WATERFALL_MODES,
  WATERFALL_SPECTRA,
  WATERFALL_SPECTRUM_LABELS,
  type WaterfallMode,
  type WaterfallSpectrum,
} from "@/types/waterfall";
import { cn } from "@/lib/utils";

interface WaterfallControlsProps {
  mode: WaterfallMode;
  onModeChange: (mode: WaterfallMode) => void;
  count: number;
  onCountChange: (count: number) => void;
  spectrum: WaterfallSpectrum;
  onSpectrumChange: (spectrum: WaterfallSpectrum) => void;
  channel: number;
  channelCount: number;
  onChannelChange: (channel: number) => void;
  onReshuffle: () => void;
  totalAvailable: number;
  disabled?: boolean;
}

export function WaterfallControls({
  mode,
  onModeChange,
  count,
  onCountChange,
  spectrum,
  onSpectrumChange,
  channel,
  channelCount,
  onChannelChange,
  onReshuffle,
  totalAvailable,
  disabled = false,
}: WaterfallControlsProps) {
  const maxCount = Math.max(1, totalAvailable || 200);

  return (
    <div className={cn("grid grid-cols-2 gap-3 lg:grid-cols-5")}>
      <FormField label="Selection" compact>
        <select
          className={analysisSelectClass}
          value={mode}
          onChange={(e) => onModeChange(e.target.value as WaterfallMode)}
          disabled={disabled}
        >
          {WATERFALL_MODES.map((value) => (
            <option key={value} value={value}>
              {WATERFALL_MODE_LABELS[value]}
            </option>
          ))}
        </select>
      </FormField>

      <FormField label="Captures (N)" compact>
        <TextInput
          type="number"
          min={1}
          max={maxCount}
          className={analysisInputClass}
          value={count}
          disabled={disabled}
          onChange={(e) => {
            const next = Number(e.target.value);
            if (!Number.isFinite(next)) return;
            onCountChange(Math.max(1, Math.min(Math.round(next), maxCount)));
          }}
        />
      </FormField>

      <FormField label="Spectrum" compact>
        <select
          className={analysisSelectClass}
          value={spectrum}
          onChange={(e) => onSpectrumChange(e.target.value as WaterfallSpectrum)}
          disabled={disabled}
        >
          {WATERFALL_SPECTRA.map((value) => (
            <option key={value} value={value}>
              {WATERFALL_SPECTRUM_LABELS[value]}
            </option>
          ))}
        </select>
      </FormField>

      <FormField label="Channel" compact>
        <select
          className={analysisSelectClass}
          value={channel}
          onChange={(e) => onChannelChange(Number(e.target.value))}
          disabled={disabled}
        >
          {Array.from({ length: Math.max(1, channelCount) }, (_, i) => (
            <option key={i} value={i}>
              CH {i + 1} (ch{i})
            </option>
          ))}
        </select>
      </FormField>

      <div className="flex items-end">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="w-full"
          icon={<Shuffle size={14} />}
          onClick={onReshuffle}
          disabled={disabled || mode !== "random"}
          title={
            mode === "random"
              ? "Draw a different random set of captures"
              : "Available when Selection is Random"
          }
        >
          Re-shuffle
        </Button>
      </div>
    </div>
  );
}
