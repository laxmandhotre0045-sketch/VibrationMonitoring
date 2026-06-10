import React from "react";
import { Activity } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
import {
  getAIReadinessScore,
  getSensorCoverage,
  getDataCompleteness,
  getDiagnosticReadiness,
  getPMReadiness,
} from "@/lib/form-intelligence";
import { ProgressRing } from "./industrial/ProgressRing";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

interface AssetHealthPanelProps {
  data: EquipmentFormData;
}

const RING_CONFIG = [
  { key: "ai", label: "AI Readiness", getValue: getAIReadinessScore, color: "#D98C00" },
  { key: "sensor", label: "Sensor Coverage", getValue: getSensorCoverage, color: "#D98C00" },
  { key: "data", label: "Data Completeness", getValue: getDataCompleteness, color: "#B86E00" },
  { key: "diag", label: "Diagnostic Readiness", getValue: getDiagnosticReadiness, color: "#D98C00" },
  { key: "pm", label: "PM Readiness", getValue: getPMReadiness, color: "#B86E00" },
] as const;

export function AssetHealthPanel({ data }: AssetHealthPanelProps) {
  return (
    <div className={cn("bg-card border border-border rounded-xl", cardHover.panel)}>
      <div className="px-8 py-5 border-b border-border flex items-center gap-3">
        <Activity size={20} className="text-signal-dark" />
        <h3 className="text-section-title text-brand">Asset Intelligence</h3>
      </div>
      <div className="p-8 space-y-6">
        {RING_CONFIG.map((ring) => (
          <ProgressRing
            key={ring.key}
            value={ring.getValue(data)}
            label={ring.label}
            color={ring.color}
            size={60}
            strokeWidth={5}
          />
        ))}
      </div>
    </div>
  );
}
