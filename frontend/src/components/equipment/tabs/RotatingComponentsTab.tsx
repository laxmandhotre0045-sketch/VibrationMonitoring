import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { RotateCw } from "lucide-react";
import { EquipmentFormData } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { FormField, TextInput, SelectInput, TextareaInput } from "@/components/ui/FormField";
import { BearingCatalogField } from "@/components/equipment/bearing/BearingCatalogField";

const POLE_COUNTS = [2, 4, 6, 8, 10, 12];
const DIRECTIONS = ["Clockwise", "Counter-Clockwise", "Bidirectional"];

export function RotatingComponentsTab() {
  const { control, watch } = useFormContext<EquipmentFormData>();
  const machineType = watch("machine_type");
  const driveType = watch("drive_type");

  const isMotorType = ["Motor", "Generator", "DG Set"].includes(machineType ?? "");
  const isFanType = ["Fan", "Blower"].includes(machineType ?? "");
  const isPumpType = machineType === "Pump";
  const isGearboxType = machineType === "Gearbox" || driveType === "Gear Drive";

  return (
    <div className="flex flex-col gap-g5">
      <SectionCard
        title="Bearing Details"
        description="Optional — equipment can be saved without these. Fill them in to unlock bearing-frequency (BPFO/BPFI) diagnostics."
        icon={<RotateCw size={15} />}
      >
        <div className="flex flex-col gap-g4">
          <FormField label="Bearing Details">
            <Controller name="bearing_details" control={control} render={({ field }) => (
              <TextareaInput {...field} value={field.value ?? ""} rows={2} placeholder="Bearing type, size, and details…" />
            )} />
          </FormField>

          {/* One block per bearing position. Each resolves against the fault
              frequency catalogue: enter the Bearing ID, or search the part
              number, and the manufacturer, type, element count and the four
              defect frequencies fill in. */}
          <div className="grid grid-cols-1 gap-g4 xl:grid-cols-2">
            <Controller
              name="bearing_de_catalog_id"
              control={control}
              render={({ field: catalogField }) => (
                <Controller
                  name="bearing_number_de"
                  control={control}
                  render={({ field: numberField }) => (
                    <BearingCatalogField
                      label="Drive End (DE)"
                      numberLabel="Bearing Number (DE)"
                      numberPlaceholder="e.g. 6205"
                      catalogId={catalogField.value ?? null}
                      onCatalogIdChange={catalogField.onChange}
                      bearingNumber={numberField.value ?? ""}
                      onBearingNumberChange={numberField.onChange}
                    />
                  )}
                />
              )}
            />

            <Controller
              name="bearing_nde_catalog_id"
              control={control}
              render={({ field: catalogField }) => (
                <Controller
                  name="bearing_number_nde"
                  control={control}
                  render={({ field: numberField }) => (
                    <BearingCatalogField
                      label="Non-Drive End (NDE)"
                      numberLabel="Bearing Number (NDE)"
                      numberPlaceholder="e.g. 6204"
                      catalogId={catalogField.value ?? null}
                      onCatalogIdChange={catalogField.onChange}
                      bearingNumber={numberField.value ?? ""}
                      onBearingNumberChange={numberField.onChange}
                    />
                  )}
                />
              )}
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Rotating Components"
        description="Optional — used to derive shaft and blade-pass frequencies when provided."
        icon={<RotateCw size={15} />}
      >
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-g4">
          {isMotorType && (
            <FormField label="Motor Pole Count">
              <Controller name="motor_pole_count" control={control} render={({ field }) => (
                <SelectInput
                  {...field}
                  value={field.value?.toString() || ""}
                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                  options={POLE_COUNTS}
                  placeholder="Select poles"
                />
              )} />
            </FormField>
          )}
          {isFanType && (
            <FormField label="Number of Fan Blades">
              <Controller name="fan_blades" control={control} render={({ field }) => (
                <TextInput type="number" min="1" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseInt(e.target.value))} placeholder="e.g. 6" />
              )} />
            </FormField>
          )}
          {isPumpType && (
            <FormField label="Number of Pump Vanes">
              <Controller name="pump_vanes" control={control} render={({ field }) => (
                <TextInput type="number" min="1" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseInt(e.target.value))} placeholder="e.g. 7" />
              )} />
            </FormField>
          )}
          {isGearboxType && (
            <>
              <FormField label="Gearbox Ratio">
                <Controller name="gearbox_ratio" control={control} render={({ field }) => (
                  <TextInput type="number" step="0.001" min="0" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseFloat(e.target.value))} placeholder="e.g. 4.2" />
                )} />
              </FormField>
              <FormField label="Number of Gear Teeth">
                <Controller name="gear_teeth" control={control} render={({ field }) => (
                  <TextInput type="number" min="1" {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value === "" ? null : parseInt(e.target.value))} placeholder="e.g. 32" />
                )} />
              </FormField>
            </>
          )}
          <FormField label="Direction of Rotation">
            <Controller name="direction_of_rotation" control={control} render={({ field }) => (
              <SelectInput {...field} value={field.value || ""} options={DIRECTIONS} placeholder="Select direction" />
            )} />
          </FormField>
        </div>
      </SectionCard>
    </div>
  );
}
