import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { Settings } from "lucide-react";
import { EquipmentFormData } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { FormField, TextInput, SelectInput } from "@/components/ui/FormField";

const DRIVE_TYPES = ["Direct Drive", "Belt Drive", "Gear Drive", "Chain Drive", "VFD Drive", "Hydraulic Drive"];
const LOAD_TYPES = ["Constant Load", "Variable Load", "Intermittent Load", "Cyclic Load", "Shock Load"];
const FOUNDATION_TYPES = ["Concrete Foundation", "Steel Structure", "Skid Mounted", "Base Frame", "Suspended Structure"];
const COUPLING_TYPES = ["Flexible", "Grid", "Gear", "Jaw", "Disc", "Tyre", "Chain", "Fluid", "Direct"];

export function MechanicalDetailsTab() {
  const { control } = useFormContext<EquipmentFormData>();

  return (
    <SectionCard title="Mechanical Details" icon={<Settings size={15} />}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-g4">
        <FormField label="Rated Power">
          <Controller name="rated_power_kw" control={control} render={({ field }) => (
            <TextInput type="number" step="0.01" min="0" unit="kW" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseFloat(e.target.value))} placeholder="e.g. 75" />
          )} />
        </FormField>
        <FormField label="Rated RPM">
          <Controller name="rated_rpm" control={control} render={({ field }) => (
            <TextInput type="number" min="0" unit="RPM" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseInt(e.target.value))} placeholder="e.g. 1480" />
          )} />
        </FormField>
        <FormField label="Drive Type">
          <Controller
            name="drive_type"
            control={control}
            render={({ field }) => (
              <SelectInput {...field} value={field.value || ""} options={DRIVE_TYPES} placeholder="Select drive type" />
            )}
          />
        </FormField>
        <FormField label="Load Type">
          <Controller
            name="load_type"
            control={control}
            render={({ field }) => (
              <SelectInput {...field} value={field.value || ""} options={LOAD_TYPES} placeholder="Select load type" />
            )}
          />
        </FormField>
        <FormField label="Foundation Type">
          <Controller
            name="foundation_type"
            control={control}
            render={({ field }) => (
              <SelectInput {...field} value={field.value || ""} options={FOUNDATION_TYPES} placeholder="Select foundation" />
            )}
          />
        </FormField>
        <FormField label="Coupling Details">
          <Controller
            name="coupling_details"
            control={control}
            render={({ field }) => (
              <SelectInput {...field} value={field.value || ""} options={COUPLING_TYPES} placeholder="Select coupling" />
            )}
          />
        </FormField>
      </div>
    </SectionCard>
  );
}
