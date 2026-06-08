import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { Activity, Wrench } from "lucide-react";
import { EquipmentFormData } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { FormField, TextInput, SelectInput, TextareaInput, RangeInput } from "@/components/ui/FormField";
import { MultiSelect } from "@/components/ui/MultiSelect";

const LUBRICATION_TYPES = ["Grease", "Oil Bath", "Oil Mist", "Forced Oil", "Splash Lubrication", "Automatic Lubrication"];
const OPERATING_ENVIRONMENTS = [
  "Indoor", "Outdoor", "Dusty", "Wet Area", "High Temperature", "Low Temperature",
  "Corrosive Environment", "Chemical Area", "Hazardous Area", "Marine Environment",
  "Mining Environment", "Clean Room", "Food Grade Area",
];

export function OperatingProcessTab() {
  const { control } = useFormContext<EquipmentFormData>();

  return (
    <div className="flex flex-col gap-11">
      <SectionCard title="Operating & Process" icon={<Activity size={15} />}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="flex flex-col gap-6">
            <FormField label="Operating Speed Range (RPM)">
              <Controller
                name="operating_speed_min"
                control={control}
                render={({ field: fieldMin }) => (
                  <Controller
                    name="operating_speed_max"
                    control={control}
                    render={({ field: fieldMax }) => (
                      <RangeInput
                        unit="RPM"
                        valueMin={fieldMin.value ?? ""}
                        valueMax={fieldMax.value ?? ""}
                        onChangeMin={(v) => fieldMin.onChange(v ? Number(v) : null)}
                        onChangeMax={(v) => fieldMax.onChange(v ? Number(v) : null)}
                      />
                    )}
                  />
                )}
              />
            </FormField>
            <FormField label="Load Range (%)">
              <Controller
                name="load_range_min"
                control={control}
                render={({ field: fieldMin }) => (
                  <Controller
                    name="load_range_max"
                    control={control}
                    render={({ field: fieldMax }) => (
                      <RangeInput
                        unit="%"
                        valueMin={fieldMin.value ?? ""}
                        valueMax={fieldMax.value ?? ""}
                        onChangeMin={(v) => fieldMin.onChange(v ? Number(v) : null)}
                        onChangeMax={(v) => fieldMax.onChange(v ? Number(v) : null)}
                      />
                    )}
                  />
                )}
              />
            </FormField>
            <FormField label="Normal Operating Load (%)">
              <Controller name="normal_operating_load" control={control} render={({ field }) => (
              <TextInput type="number" min="0" max="100" unit="%" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseFloat(e.target.value))} placeholder="e.g. 75" />
            )} />
            </FormField>
          </div>
          <FormField label="Process Details" className="h-full">
            <Controller name="process_details" control={control} render={({ field }) => (
              <TextareaInput {...field} value={field.value ?? ""} rows={7} placeholder="Process description..." className="h-full" />
            )} />
          </FormField>
        </div>

        <div className="mt-6">
          <FormField label="Operating Environment">
            <Controller
              name="operating_environment"
              control={control}
              render={({ field }) => (
                <MultiSelect options={OPERATING_ENVIRONMENTS} value={field.value || []} onChange={field.onChange} placeholder="Select environments..." />
              )}
            />
          </FormField>
        </div>
      </SectionCard>

      <SectionCard title="Lubrication & Maintenance" icon={<Wrench size={15} />}>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          <FormField label="Lubrication Type">
            <Controller
              name="lubrication_type"
              control={control}
              render={({ field }) => (
                <SelectInput {...field} value={field.value || ""} options={LUBRICATION_TYPES} placeholder="Select type" />
              )}
            />
          </FormField>
          <FormField label="Installation Date">
            <Controller name="installation_date" control={control} render={({ field }) => (
              <TextInput type="date" {...field} value={field.value ?? ""} />
            )} />
          </FormField>
          <FormField label="Last Maintenance Date">
            <Controller name="last_maintenance_date" control={control} render={({ field }) => (
              <TextInput type="date" {...field} value={field.value ?? ""} />
            )} />
          </FormField>
          <FormField label="Maintenance Notes" className="md:col-span-2 lg:col-span-4">
            <Controller name="maintenance_notes" control={control} render={({ field }) => (
              <TextareaInput {...field} value={field.value ?? ""} rows={3} placeholder="Maintenance notes..." />
            )} />
          </FormField>
        </div>
      </SectionCard>
    </div>
  );
}
