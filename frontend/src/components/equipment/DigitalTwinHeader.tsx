import React from "react";
import type { EquipmentFormData } from "@/types/equipment";
import { VibrationIntelligenceBg } from "@/components/brand/VibrationIntelligenceBg";

interface DigitalTwinHeaderProps {
  data: EquipmentFormData;
  isEdit: boolean;
}

export function DigitalTwinHeader({ data, isEdit }: DigitalTwinHeaderProps) {
  return (
    <div className="content-card relative overflow-hidden">
      <VibrationIntelligenceBg variant="hero" />
      <div className="relative z-10 px-8 py-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand/50 mb-2">
          Equipment Master
        </p>
        <h1 className="text-2xl font-semibold text-brand tracking-tight">
          {isEdit ? "Edit Digital Twin" : "Create Digital Twin"}
        </h1>
        {data.machine_name && (
          <p className="text-base text-muted-foreground mt-2">
            {data.machine_name}
            {data.machine_id && <span className="text-muted-foreground/70"> · {data.machine_id}</span>}
          </p>
        )}
      </div>
    </div>
  );
}
