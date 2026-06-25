import React from "react";
import { Shield } from "lucide-react";
import { CRITICALITY_IMPACT } from "@/lib/industrial-metadata";
import { cn } from "@/lib/utils";

interface CriticalityIndicatorProps {
  level: string;
}

export function CriticalityIndicator({ level }: CriticalityIndicatorProps) {
  if (!level || !CRITICALITY_IMPACT[level]) return null;
  const cfg = CRITICALITY_IMPACT[level];

  return (
    <div className={cn("mt-4 p-4 rounded-lg border", cfg.bg, cfg.border)}>
      <div className="flex items-center gap-2.5 mb-2">
        <Shield size={16} className={cfg.color} />
        <span className={cn("text-base font-bold tracking-wide", cfg.color)}>{cfg.label}</span>
        <span className="text-base font-medium text-muted-foreground">· Reliability Impact</span>
      </div>
      <p className="text-base font-normal text-foreground leading-relaxed">{cfg.impact}</p>
    </div>
  );
}
