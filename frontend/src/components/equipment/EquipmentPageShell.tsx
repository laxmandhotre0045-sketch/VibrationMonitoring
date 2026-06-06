import React from "react";
import { VibrationIntelligenceBg } from "@/components/brand/VibrationIntelligenceBg";

interface EquipmentPageShellProps {
  children: React.ReactNode;
}

/** Equipment Master pages — vibration-intelligence page canvas behind content */
export function EquipmentPageShell({ children }: EquipmentPageShellProps) {
  return (
    <div className="relative">
      <VibrationIntelligenceBg variant="page" className="absolute inset-0 -z-10 min-h-full" />
      <div className="relative">{children}</div>
    </div>
  );
}
