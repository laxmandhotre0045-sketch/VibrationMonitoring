import React from "react";
import type { EquipmentFormData } from "@/types/equipment";
import { SensorPulseRings } from "@/components/brand/SensorPulseRings";
import { cn } from "@/lib/utils";
import { cardSizing } from "@/lib/card-sizing";
import { cardHover } from "@/lib/card-hover";

interface MachineVisualizationPanelProps {
  data: EquipmentFormData;
  className?: string;
}

function MachineIllustration({ type }: { type: string }) {
  const stroke = "#15366D";
  const accent = "#F5A623";
  const light = "#E5E7EB";

  const illustrations: Record<string, React.ReactNode> = {
    Pump: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <rect x="20" y="45" width="60" height="30" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="80" cy="60" r="18" fill="none" stroke={stroke} strokeWidth="2" />
        <line x1="98" y1="60" x2="140" y2="60" stroke={stroke} strokeWidth="2" />
        <rect x="140" y="40" width="40" height="40" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="30" cy="60" r="5" fill={accent} opacity="0.75" />
        <circle cx="160" cy="50" r="4" fill={accent} opacity="0.75" />
      </svg>
    ),
    Motor: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <rect x="50" y="35" width="100" height="50" rx="6" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="70" cy="60" r="12" fill="none" stroke={light} strokeWidth="1.5" />
        <circle cx="130" cy="60" r="12" fill="none" stroke={light} strokeWidth="1.5" />
        <line x1="30" y1="60" x2="50" y2="60" stroke={stroke} strokeWidth="2" />
        <line x1="150" y1="60" x2="170" y2="60" stroke={stroke} strokeWidth="2" />
        <circle cx="70" cy="60" r="3" fill={accent} />
        <circle cx="130" cy="60" r="3" fill={accent} />
      </svg>
    ),
    Fan: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <circle cx="80" cy="60" r="30" fill="none" stroke={stroke} strokeWidth="2" />
        <ellipse cx="80" cy="60" rx="25" ry="8" fill="none" stroke={light} strokeWidth="1" />
        <ellipse cx="80" cy="60" rx="25" ry="8" fill="none" stroke={light} strokeWidth="1" transform="rotate(60 80 60)" />
        <ellipse cx="80" cy="60" rx="25" ry="8" fill="none" stroke={light} strokeWidth="1" transform="rotate(120 80 60)" />
        <rect x="130" y="45" width="40" height="30" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="80" cy="60" r="3" fill={accent} />
      </svg>
    ),
    Blower: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <circle cx="75" cy="60" r="28" fill="none" stroke={stroke} strokeWidth="2" />
        <ellipse cx="75" cy="60" rx="22" ry="7" fill="none" stroke={light} strokeWidth="1" />
        <ellipse cx="75" cy="60" rx="22" ry="7" fill="none" stroke={light} strokeWidth="1" transform="rotate(72 75 60)" />
        <rect x="125" y="42" width="45" height="36" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="75" cy="60" r="3" fill={accent} />
      </svg>
    ),
    Compressor: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <rect x="40" y="30" width="50" height="60" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <rect x="110" y="40" width="50" height="40" rx="20" fill="none" stroke={stroke} strokeWidth="2" />
        <line x1="90" y1="60" x2="110" y2="60" stroke={stroke} strokeWidth="2" />
        <circle cx="55" cy="50" r="3" fill={accent} />
        <circle cx="135" cy="60" r="3" fill={accent} />
      </svg>
    ),
    Gearbox: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <circle cx="70" cy="60" r="22" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="130" cy="60" r="16" fill="none" stroke={stroke} strokeWidth="2" />
        <line x1="92" y1="60" x2="114" y2="60" stroke={stroke} strokeWidth="2" />
        <circle cx="70" cy="38" r="3" fill={accent} />
        <circle cx="130" cy="44" r="3" fill={accent} />
      </svg>
    ),
    Generator: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <rect x="60" y="35" width="80" height="50" rx="4" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="85" cy="60" r="10" fill="none" stroke={light} strokeWidth="1.5" />
        <circle cx="115" cy="60" r="10" fill="none" stroke={light} strokeWidth="1.5" />
        <circle cx="85" cy="60" r="2.5" fill={accent} />
        <circle cx="115" cy="60" r="2.5" fill={accent} />
      </svg>
    ),
    Conveyor: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <line x1="20" y1="70" x2="180" y2="70" stroke={stroke} strokeWidth="2" />
        <circle cx="40" cy="70" r="12" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="160" cy="70" r="12" fill="none" stroke={stroke} strokeWidth="2" />
        <rect x="60" y="62" width="80" height="6" fill={light} />
        <circle cx="40" cy="58" r="2.5" fill={accent} />
        <circle cx="160" cy="58" r="2.5" fill={accent} />
      </svg>
    ),
    Crusher: (
      <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        <rect x="50" y="25" width="100" height="70" rx="6" fill="none" stroke={stroke} strokeWidth="2" />
        <line x1="70" y1="40" x2="130" y2="80" stroke={light} strokeWidth="2" />
        <line x1="130" y1="40" x2="70" y2="80" stroke={light} strokeWidth="2" />
        <circle cx="60" cy="90" r="8" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="140" cy="90" r="8" fill="none" stroke={stroke} strokeWidth="2" />
        <circle cx="60" cy="90" r="2.5" fill={accent} />
        <circle cx="140" cy="90" r="2.5" fill={accent} />
      </svg>
    ),
  };

  const match = Object.keys(illustrations).find((k) => k.toLowerCase() === type.toLowerCase());
  if (match) return illustrations[match];

  return (
    <svg viewBox="0 0 200 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
      <rect x="50" y="35" width="100" height="50" rx="6" fill="none" stroke={light} strokeWidth="1.5" strokeDasharray="6" />
      <circle cx="100" cy="60" r="18" fill="none" stroke={light} strokeWidth="1.5" />
    </svg>
  );
}

export function MachineVisualizationPanel({ data, className }: MachineVisualizationPanelProps) {
  const machineType = data.machine_type || "";

  return (
    <div className={cn("content-card card-auto rounded-lg", cardHover.soft, className)}>
      <div className="px-g4 py-g2 border-b border-border">
        <p className="text-overline">
          Asset Preview
        </p>
        <p className="text-base font-semibold text-brand truncate mt-g1">
          {machineType || "No type selected"}
          {data.machine_name && (
            <span className="text-muted-foreground font-normal"> · {data.machine_name}</span>
          )}
        </p>
      </div>

      <div className="relative flex items-center justify-center px-3 py-3 overflow-hidden">
        <SensorPulseRings />
        <div className="relative w-full aspect-[5/3] max-h-[200px] min-h-[140px]">
          <MachineIllustration type={machineType} />
        </div>
      </div>
    </div>
  );
}
