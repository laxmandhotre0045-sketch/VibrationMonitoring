import React, { useRef, useState } from "react";
import { useFormContext, Controller } from "react-hook-form";
import { MapPin, Tag, Factory, Upload, X } from "lucide-react";
import { EquipmentFormData, CRITICALITY_DOT } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { FormField, TextInput, SelectInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

const MACHINE_TYPES = [
  "Motor", "Pump", "Fan", "Blower", "Compressor", "Gearbox",
  "Turbine", "Generator", "DG Set", "Conveyor", "Crusher", "Mixer", "Agitator",
];
const CRITICALITY = ["Low", "Medium", "High", "Critical"];

interface BasicDetailsTabProps {
  onImageSelect: (file: File | null) => void;
}

export function BasicDetailsTab({ onImageSelect }: BasicDetailsTabProps) {
  const { control } = useFormContext<EquipmentFormData>();
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onImageSelect(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const clearImage = () => {
    setImagePreview(null);
    onImageSelect(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-11">
      <SectionCard title="Location Hierarchy" icon={<MapPin size={15} />}>
        <div className="flex flex-col gap-6">
          <FormField label="Plant Name">
            <Controller name="plant_name" control={control} render={({ field }) => (
              <TextInput {...field} value={field.value ?? ""} placeholder="e.g. Pune Plant" />
            )} />
          </FormField>
          <FormField label="Area">
            <Controller name="area" control={control} render={({ field }) => (
              <TextInput {...field} value={field.value ?? ""} placeholder="e.g. Utilities" />
            )} />
          </FormField>
          <FormField label="Line">
            <Controller name="line" control={control} render={({ field }) => (
              <TextInput {...field} value={field.value ?? ""} placeholder="e.g. Cooling Water Line" />
            )} />
          </FormField>
        </div>
      </SectionCard>

      <SectionCard title="Machine Identification" icon={<Tag size={15} />}>
        <div className="flex flex-col gap-6">
          <FormField label="Machine Name">
            <Controller name="machine_name" control={control} render={({ field }) => (
              <TextInput {...field} value={field.value ?? ""} placeholder="e.g. Cooling Water Pump P-204" />
            )} />
          </FormField>
          <FormField label="Machine ID / Asset Code">
            <Controller name="machine_id" control={control} render={({ field }) => (
              <TextInput {...field} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value || null)} placeholder="e.g. PUMP-P204" />
            )} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Machine Type">
              <Controller name="machine_type" control={control} render={({ field }) => (
                <SelectInput {...field} value={field.value ?? ""} options={MACHINE_TYPES} placeholder="Select type" />
              )} />
            </FormField>
            <FormField label="Machine Criticality">
              <Controller name="machine_criticality" control={control} render={({ field }) => (
                <div className="relative">
                  <select
                    {...field}
                    value={field.value ?? ""}
                    className="w-full pl-8 pr-4 py-3 text-base border border-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.22)] appearance-none cursor-pointer"
                  >
                    <option value="">Select</option>
                    {CRITICALITY.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  {field.value && (
                    <span className={cn("absolute left-2.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full", CRITICALITY_DOT[field.value])} />
                  )}
                </div>
              )} />
            </FormField>
          </div>
        </div>
      </SectionCard>

      <div className="flex flex-col gap-11">
        <SectionCard title="Manufacturer & Model" icon={<Factory size={15} />}>
          <div className="flex flex-col gap-6">
            <FormField label="Manufacturer">
              <Controller name="manufacturer" control={control} render={({ field }) => (
                <TextInput {...field} value={field.value ?? ""} placeholder="e.g. KSB" />
              )} />
            </FormField>
            <FormField label="Model">
              <Controller name="model" control={control} render={({ field }) => (
                <TextInput {...field} value={field.value ?? ""} placeholder="e.g. Etanorm SYT 100-250" />
              )} />
            </FormField>
            <FormField label="Serial Number">
              <Controller name="serial_number" control={control} render={({ field }) => (
                <TextInput {...field} value={field.value ?? ""} placeholder="e.g. KSB20240521001" />
              )} />
            </FormField>
          </div>
        </SectionCard>

        <SectionCard title="Equipment Image" icon={<Upload size={15} />}>
          {imagePreview ? (
            <div className="relative">
              <img src={imagePreview} alt="Equipment" className="w-full h-36 object-contain rounded-md border border-border bg-white" />
              <button
                type="button"
                onClick={clearImage}
                className="absolute top-2 right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600"
              >
                <X size={12} />
              </button>
            </div>
          ) : (
            <div
              className="border border-dashed border-border rounded-lg p-8 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-signal-light/50 hover:bg-surface transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={22} className="text-signal-dark" />
              <p className="text-base font-medium text-foreground">Upload image</p>
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageChange} />
        </SectionCard>
      </div>
    </div>
  );
}
