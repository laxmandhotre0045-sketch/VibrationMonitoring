import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { Brain, CheckCircle2, XCircle, MapPin, Tag, Settings, RotateCw, Activity, Radio } from "lucide-react";
import { EquipmentFormData, CRITICALITY_COLORS, CRITICALITY_DOT } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { SelectInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

const ASSET_STATUS = ["Active", "Inactive", "Under Maintenance", "Decommissioned"];

function ReviewRow({ label, value }: { label: string; value?: string | number | null }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-500 w-40 shrink-0">{label}</span>
      <span className="text-sm font-medium text-gray-800">{String(value)}</span>
    </div>
  );
}

function ReviewSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 border-b border-gray-100">
        <span className="text-blue-600">{icon}</span>
        <span className="text-sm font-semibold text-gray-700">{title}</span>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

export function ReviewSaveTab() {
  const { watch, control } = useFormContext<EquipmentFormData>();
  const data = watch();

  const checks = [
    {
      label: "Machine Train Configured",
      key: "machine_train_configured" as keyof EquipmentFormData,
      value: data.machine_train_configured,
      desc: "Machine type and hierarchy defined",
    },
    {
      label: "Asset Status Set",
      key: null,
      value: !!data.asset_status,
      desc: "Operational status of this asset",
    },
    {
      label: "Sensor Coverage",
      key: null,
      value: (data.sensors?.length || 0) > 0,
      desc: "At least one sensor configured",
    },
    {
      label: "Bearing Database Mapped",
      key: "bearing_database_mapped" as keyof EquipmentFormData,
      value: data.bearing_database_mapped,
      desc: "Bearing numbers (DE/NDE) entered",
    },
    {
      label: "Operating Mode Configured",
      key: "operating_mode_configured" as keyof EquipmentFormData,
      value: data.operating_mode_configured || (!!data.operating_speed_min && !!data.operating_speed_max),
      desc: "Speed range and load range defined",
    },
  ];

  const score = Math.round((checks.filter((c) => c.value).length / checks.length) * 100);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      {/* Left: Summary */}
      <div className="lg:col-span-2 flex flex-col gap-4">
        <ReviewSection title="Location & Identity" icon={<MapPin size={14} />}>
          <ReviewRow label="Plant Name" value={data.plant_name} />
          <ReviewRow label="Area" value={data.area} />
          <ReviewRow label="Line" value={data.line} />
          <ReviewRow label="Machine Name" value={data.machine_name} />
          <ReviewRow label="Machine ID" value={data.machine_id} />
          <ReviewRow label="Machine Type" value={data.machine_type} />
          {data.machine_criticality && (
            <div className="flex items-center gap-2 py-1.5 border-b border-gray-50">
              <span className="text-xs text-gray-500 w-40 shrink-0">Criticality</span>
              <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", CRITICALITY_COLORS[data.machine_criticality])}>
                {data.machine_criticality}
              </span>
            </div>
          )}
          <ReviewRow label="Manufacturer" value={data.manufacturer} />
          <ReviewRow label="Model" value={data.model} />
          <ReviewRow label="Serial Number" value={data.serial_number} />
        </ReviewSection>

        <ReviewSection title="Mechanical Details" icon={<Settings size={14} />}>
          <ReviewRow label="Rated Power" value={data.rated_power_kw ? `${data.rated_power_kw} kW` : null} />
          <ReviewRow label="Rated RPM" value={data.rated_rpm ? `${data.rated_rpm} RPM` : null} />
          <ReviewRow label="Drive Type" value={data.drive_type} />
          <ReviewRow label="Load Type" value={data.load_type} />
          <ReviewRow label="Foundation Type" value={data.foundation_type} />
          <ReviewRow label="Coupling Details" value={data.coupling_details} />
        </ReviewSection>

        <ReviewSection title="Rotating Components" icon={<RotateCw size={14} />}>
          <ReviewRow label="Bearing Number DE" value={data.bearing_number_de} />
          <ReviewRow label="Bearing Number NDE" value={data.bearing_number_nde} />
          <ReviewRow label="Motor Pole Count" value={data.motor_pole_count} />
          <ReviewRow label="Fan Blades" value={data.fan_blades} />
          <ReviewRow label="Pump Vanes" value={data.pump_vanes} />
          <ReviewRow label="Gearbox Ratio" value={data.gearbox_ratio} />
          <ReviewRow label="Gear Teeth" value={data.gear_teeth} />
          <ReviewRow label="Direction" value={data.direction_of_rotation} />
        </ReviewSection>

        <ReviewSection title="Operating & Process" icon={<Activity size={14} />}>
          <ReviewRow
            label="Speed Range"
            value={data.operating_speed_min && data.operating_speed_max
              ? `${data.operating_speed_min} – ${data.operating_speed_max} RPM` : null}
          />
          <ReviewRow
            label="Load Range"
            value={data.load_range_min && data.load_range_max
              ? `${data.load_range_min} – ${data.load_range_max}%` : null}
          />
          <ReviewRow label="Normal Op. Load" value={data.normal_operating_load ? `${data.normal_operating_load}%` : null} />
          <ReviewRow label="Lubrication" value={data.lubrication_type} />
          <ReviewRow label="Installation Date" value={data.installation_date} />
          <ReviewRow label="Last Maintenance" value={data.last_maintenance_date} />
          {(data.operating_environment?.length || 0) > 0 && (
            <div className="flex items-start gap-2 py-1.5">
              <span className="text-xs text-gray-500 w-40 shrink-0">Environment</span>
              <div className="flex flex-wrap gap-1">
                {data.operating_environment?.map((e) => (
                  <span key={e} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{e}</span>
                ))}
              </div>
            </div>
          )}
        </ReviewSection>

        <ReviewSection title="Sensors" icon={<Radio size={14} />}>
          {(data.sensors?.length || 0) === 0 ? (
            <p className="text-sm text-gray-400 py-1">No additional sensors configured.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {data.sensors?.map((s, i) => (
                <div key={i} className="flex flex-wrap gap-2 py-1.5 border-b border-gray-50 last:border-0">
                  <span className="text-xs font-semibold text-gray-700">Sensor {i + 1}:</span>
                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">{s.sensor_type}</span>
                  <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{s.mounting_location}</span>
                  <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{s.orientation}</span>
                </div>
              ))}
            </div>
          )}
        </ReviewSection>
      </div>

      {/* Right: AI Readiness */}
      <div className="flex flex-col gap-5">
        <SectionCard title="AI Readiness" icon={<Brain size={15} />}>
          {/* Score */}
          <div className="flex flex-col items-center mb-5 pt-2">
            <div className="relative w-24 h-24">
              <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" strokeWidth="10" />
                <circle
                  cx="50" cy="50" r="40" fill="none"
                  stroke={score >= 80 ? "#16a34a" : score >= 60 ? "#2563eb" : score >= 40 ? "#f59e0b" : "#ef4444"}
                  strokeWidth="10"
                  strokeDasharray={`${(score / 100) * 251.2} 251.2`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-gray-800">{score}%</span>
              </div>
            </div>
            <p className="text-sm font-medium text-gray-600 mt-2">
              {score === 100 ? "Fully AI-Ready!" : score >= 60 ? "Good Coverage" : "Needs More Data"}
            </p>
          </div>

          {/* Checklist */}
          <div className="flex flex-col gap-2">
            {checks.map((check) => (
              <div
                key={check.label}
                className={cn(
                  "flex items-start gap-3 p-3 rounded-lg border",
                  check.value ? "bg-green-50 border-green-200" : "bg-gray-50 border-gray-200"
                )}
              >
                {check.value
                  ? <CheckCircle2 size={16} className="text-green-600 mt-0.5 shrink-0" />
                  : <XCircle size={16} className="text-gray-300 mt-0.5 shrink-0" />}
                <div>
                  <p className={cn("text-xs font-semibold", check.value ? "text-green-800" : "text-gray-600")}>
                    {check.label}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{check.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Asset Status */}
        <SectionCard title="Asset Configuration" icon={<Brain size={15} />}>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">Asset Status</label>
              <Controller
                name="asset_status"
                control={control}
                render={({ field }) => (
                  <SelectInput {...field} value={field.value || "Active"} options={ASSET_STATUS} />
                )}
              />
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="machine_train_configured"
                className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                {...useFormContext<EquipmentFormData>().register("machine_train_configured")}
              />
              <label htmlFor="machine_train_configured" className="text-sm text-gray-700">
                Machine Train Configured
              </label>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="bearing_database_mapped"
                className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                {...useFormContext<EquipmentFormData>().register("bearing_database_mapped")}
              />
              <label htmlFor="bearing_database_mapped" className="text-sm text-gray-700">
                Bearing Database Mapped
              </label>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="operating_mode_configured"
                className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                {...useFormContext<EquipmentFormData>().register("operating_mode_configured")}
              />
              <label htmlFor="operating_mode_configured" className="text-sm text-gray-700">
                Operating Mode Configured
              </label>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
