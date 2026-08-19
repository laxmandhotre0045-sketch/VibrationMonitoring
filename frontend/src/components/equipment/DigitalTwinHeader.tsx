import React from "react";
import type { EquipmentFormData } from "@/types/equipment";
import { HeroIntelligenceBg } from "@/components/brand/HeroIntelligenceBg";

interface DigitalTwinHeaderProps {
  data: EquipmentFormData;
  isEdit: boolean;
}

export function DigitalTwinHeader({ data, isEdit }: DigitalTwinHeaderProps) {
  return (
    <div className="content-card relative overflow-hidden">
      <HeroIntelligenceBg />
      <div className="relative z-10 px-g5 py-g5">
        <p className="text-overline text-brand/65 mb-2">
          Equipment Master
        </p>
        <h1 className="text-3xl font-bold text-brand tracking-tight">
          {isEdit ? "Edit Digital Twin" : "Create Digital Twin"}
        </h1>
        {data.machine_name && (
          <p className="text-base text-helper mt-2">
            {data.machine_name}
            {data.machine_id && <span className="text-muted-foreground"> · {data.machine_id}</span>}
          </p>
        )}
      </div>
    </div>
  );
}
