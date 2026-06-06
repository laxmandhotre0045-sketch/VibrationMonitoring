import React, { useRef, useState } from "react";
import { useFormContext, Controller } from "react-hook-form";
import { MapPin, Tag, Factory, Upload, X } from "lucide-react";
import { EquipmentFormData, CRITICALITY_COLORS, CRITICALITY_DOT } from "@/types/equipment";
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
  const { register, control, watch } = useFormContext<EquipmentFormData>();
  const criticality = watch("machine_criticality");
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onImageSelect(file);
    const url = URL.createObjectURL(file);
    setImagePreview(url);
  };

  const clearImage = () => {
    setImagePreview(null);
    onImageSelect(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      {/* Location Hierarchy */}
      <SectionCard title="Location Hierarchy" icon={<MapPin size={15} />}>
        <div className="flex flex-col gap-4">
          <FormField label="Plant Name">
            <TextInput {...register("plant_name")} placeholder="e.g. Pune Plant" />
          </FormField>
          <FormField label="Area">
            <TextInput {...register("area")} placeholder="e.g. Utilities" />
          </FormField>
          <FormField label="Line">
            <TextInput {...register("line")} placeholder="e.g. Cooling Water Line" />
          </FormField>
        </div>
      </SectionCard>

      {/* Machine Identification */}
      <SectionCard title="Machine Identification" icon={<Tag size={15} />}>
        <div className="flex flex-col gap-4">
          <FormField label="Machine Name">
            <TextInput {...register("machine_name")} placeholder="e.g. Cooling Water Pump P-204" />
          </FormField>
          <FormField label="Machine ID / Asset Code">
            <TextInput {...register("machine_id")} placeholder="e.g. PUMP-P204" />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Machine Type">
              <Controller
                name="machine_type"
                control={control}
                render={({ field }) => (
                  <SelectInput
                    {...field}
                    options={MACHINE_TYPES}
                    placeholder="Select type"
                  />
                )}
              />
            </FormField>
            <FormField label="Machine Criticality">
              <Controller
                name="machine_criticality"
                control={control}
                render={({ field }) => (
                  <div className="relative">
                    <select
                      {...field}
                      className="w-full pl-7 pr-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none cursor-pointer hover:border-gray-400"
                    >
                      <option value="">Select</option>
                      {CRITICALITY.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    {field.value && (
                      <span
                        className={cn("absolute left-2.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full", CRITICALITY_DOT[field.value])}
                      />
                    )}
                  </div>
                )}
              />
            </FormField>
          </div>
        </div>
      </SectionCard>

      {/* Manufacturer & Model */}
      <div className="flex flex-col gap-5">
        <SectionCard title="Manufacturer & Model" icon={<Factory size={15} />}>
          <div className="flex flex-col gap-4">
            <FormField label="Manufacturer">
              <TextInput {...register("manufacturer")} placeholder="e.g. KSB" />
            </FormField>
            <FormField label="Model">
              <TextInput {...register("model")} placeholder="e.g. Etanorm SYT 100-250" />
            </FormField>
            <FormField label="Serial Number">
              <TextInput {...register("serial_number")} placeholder="e.g. KSB20240521001" />
            </FormField>
          </div>
        </SectionCard>

        {/* Equipment Image */}
        <SectionCard title="Equipment Image / Diagram" icon={<Upload size={15} />}>
          {imagePreview ? (
            <div className="relative">
              <img src={imagePreview} alt="Equipment" className="w-full h-40 object-contain rounded-lg border border-gray-200 bg-gray-50" />
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
              className="border-2 border-dashed border-gray-300 rounded-xl p-6 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                <Upload size={18} className="text-blue-600" />
              </div>
              <p className="text-sm font-medium text-gray-700">Upload Equipment Image</p>
              <p className="text-xs text-gray-400">PNG, JPG, WebP up to 10MB</p>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleImageChange}
          />
          {!imagePreview && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="mt-3 w-full flex items-center justify-center gap-2 text-sm text-blue-600 border border-blue-300 rounded-lg py-2 hover:bg-blue-50 transition-colors"
            >
              <Upload size={14} /> Upload Image
            </button>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
