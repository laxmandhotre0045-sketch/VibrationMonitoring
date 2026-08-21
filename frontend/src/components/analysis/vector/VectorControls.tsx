import React from "react";
import { FormField, TextInput } from "@/components/ui/FormField";
import { analysisInputClass, analysisSelectClass } from "@/components/analysis/analysis-layout";
import { VECTOR_BLOCK_SIZES, type FrequencyCandidate } from "@/types/vector";
import { cn } from "@/lib/utils";

interface VectorControlsProps {
  channel: number;
  channelCount: number;
  onChannelChange: (channel: number) => void;
  /** Empty string means "let the backend choose" (1x estimated shaft, else strongest peak). */
  targetHz: string;
  onTargetHzChange: (value: string) => void;
  candidates: FrequencyCandidate[];
  blockSize: number | "";
  onBlockSizeChange: (value: number | "") => void;
  disabled?: boolean;
}

export function VectorControls({
  channel,
  channelCount,
  onChannelChange,
  targetHz,
  onTargetHzChange,
  candidates,
  blockSize,
  onBlockSizeChange,
  disabled = false,
}: VectorControlsProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 lg:grid-cols-4")}>
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

      <FormField label="Order of interest" compact>
        <select
          className={analysisSelectClass}
          value={targetHz}
          onChange={(e) => onTargetHzChange(e.target.value)}
          disabled={disabled}
        >
          <option value="">Auto (1× estimated shaft)</option>
          {candidates.map((c) => (
            <option key={`${c.source}-${c.frequency_hz}`} value={String(c.frequency_hz)}>
              {c.label}
            </option>
          ))}
        </select>
      </FormField>

      <FormField label="Target frequency (Hz)" compact>
        <TextInput
          type="number"
          min={0}
          step="any"
          placeholder="Auto"
          className={analysisInputClass}
          value={targetHz}
          disabled={disabled}
          onChange={(e) => onTargetHzChange(e.target.value)}
        />
      </FormField>

      <FormField label="Block size (samples)" compact>
        <select
          className={analysisSelectClass}
          value={blockSize}
          onChange={(e) =>
            onBlockSizeChange(e.target.value === "" ? "" : Number(e.target.value))
          }
          disabled={disabled}
        >
          <option value="">Auto (sensor FFT size)</option>
          {VECTOR_BLOCK_SIZES.map((size) => (
            <option key={size} value={size}>
              {size.toLocaleString()}
            </option>
          ))}
        </select>
      </FormField>
    </div>
  );
}
