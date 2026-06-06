import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { RotateCw } from "lucide-react";
import { EquipmentFormData } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { FormField, TextInput, SelectInput, TextareaInput } from "@/components/ui/FormField";

const POLE_COUNTS = [2, 4, 6, 8, 10, 12];
const DIRECTIONS = ["Clockwise", "Counter-Clockwise", "Bidirectional"];

export function RotatingComponentsTab() {
  const { register, control, watch } = useFormContext<EquipmentFormData>();
  const machineType = watch("machine_type");
  const driveType = watch("drive_type");

  const isMotorType = ["Motor", "Generator", "DG Set"].includes(machineType);
  const isFanType = ["Fan", "Blower"].includes(machineType);
  const isPumpType = machineType === "Pump";
  const isGearboxType = machineType === "Gearbox" || driveType === "Gear Drive";

  return (
    <div className="flex flex-col gap-5">
      <SectionCard title="Bearing Details" icon={<RotateCw size={15} />}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <FormField label="Bearing Details" className="lg:col-span-2">
            <TextareaInput
              {...register("bearing_details")}
              rows={3}
              placeholder="Enter bearing type, size, and other details..."
            />
          </FormField>

          <div className="flex flex-col gap-4">
            <FormField label="Bearing Number (DE)">
              <TextInput {...register("bearing_number_de")} placeholder="e.g. 6205" />
            </FormField>
            <FormField label="Bearing Number (NDE)">
              <TextInput {...register("bearing_number_nde")} placeholder="e.g. 6204" />
            </FormField>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Rotating Component Specifications" icon={<RotateCw size={15} />}>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {isMotorType && (
            <FormField label="Motor Pole Count">
              <Controller
                name="motor_pole_count"
                control={control}
                render={({ field }) => (
                  <SelectInput
                    {...field}
                    value={field.value?.toString() || ""}
                    onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                    options={POLE_COUNTS}
                    placeholder="Select poles"
                  />
                )}
              />
            </FormField>
          )}

          {isFanType && (
            <FormField label="Number of Fan Blades">
              <TextInput
                type="number"
                min="1"
                {...register("fan_blades")}
                placeholder="e.g. 6"
              />
            </FormField>
          )}

          {isPumpType && (
            <FormField label="Number of Pump Vanes">
              <TextInput
                type="number"
                min="1"
                {...register("pump_vanes")}
                placeholder="e.g. 7"
              />
            </FormField>
          )}

          {isGearboxType && (
            <>
              <FormField label="Gearbox Ratio">
                <TextInput
                  type="number"
                  step="0.001"
                  min="0"
                  {...register("gearbox_ratio")}
                  placeholder="e.g. 4.2"
                />
              </FormField>
              <FormField label="Number of Gear Teeth">
                <TextInput
                  type="number"
                  min="1"
                  {...register("gear_teeth")}
                  placeholder="e.g. 32"
                />
              </FormField>
            </>
          )}

          <FormField label="Direction of Rotation">
            <Controller
              name="direction_of_rotation"
              control={control}
              render={({ field }) => (
                <SelectInput {...field} value={field.value || ""} options={DIRECTIONS} placeholder="Select direction" />
              )}
            />
          </FormField>
        </div>

        {!isMotorType && !isFanType && !isPumpType && !isGearboxType && (
          <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-100">
            <p className="text-sm text-blue-700">
              Additional component fields (pole count, fan blades, pump vanes, gearbox ratio) will appear based on the
              Machine Type and Drive Type selected in <strong>Basic Details</strong> and <strong>Mechanical Details</strong>.
            </p>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
