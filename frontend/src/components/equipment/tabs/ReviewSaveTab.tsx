import React from "react";
import { useFormContext, Controller } from "react-hook-form";
import { ClipboardCheck, MapPin, Settings, RotateCw, Activity, Radio } from "lucide-react";
import { EquipmentFormData, CRITICALITY_COLORS } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { SelectInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

const ASSET_STATUS = ["Active", "Inactive", "Under Maintenance", "Decommissioned"];

function ReviewRow({ label, value }: { label: string; value?: string | number | null }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex items-start gap-4 py-3 border-b border-border last:border-0">
      <span className="text-base text-muted-foreground w-44 shrink-0">{label}</span>
      <span className="text-base font-medium text-foreground">{String(value)}</span>
    </div>
  );
}

function ReviewSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="content-card">
      <div className="px-8 py-5 border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-brand">{icon}</span>
          <span className="text-xl font-semibold text-foreground">{title}</span>
        </div>
      </div>
      <div className="px-8 py-6">{children}</div>
    </div>
  );
}

export function ReviewSaveTab() {
  const { watch, control, register } = useFormContext<EquipmentFormData>();
  const data = watch();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-11">
      <div className="lg:col-span-2 flex flex-col gap-11">
        <ReviewSection title="Location & Identity" icon={<MapPin size={14} />}>
          <ReviewRow label="Plant Name" value={data.plant_name} />
          <ReviewRow label="Area" value={data.area} />
          <ReviewRow label="Line" value={data.line} />
          <ReviewRow label="Machine Name" value={data.machine_name} />
          <ReviewRow label="Machine ID" value={data.machine_id} />
          <ReviewRow label="Machine Type" value={data.machine_type} />
          {data.machine_criticality && (
            <div className="flex items-center gap-2 py-3 border-b border-border">
              <span className="text-base text-muted-foreground w-44 shrink-0">Criticality</span>
              <span className={cn("text-sm font-semibold px-2.5 py-1 rounded-md border", CRITICALITY_COLORS[data.machine_criticality])}>
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
            <div className="flex items-start gap-4 py-3">
              <span className="text-base text-muted-foreground w-44 shrink-0">Environment</span>
              <div className="flex flex-wrap gap-1">
                {data.operating_environment?.map((e) => (
                  <span key={e} className="text-sm bg-surface text-foreground px-2.5 py-1 rounded-md border border-border">{e}</span>
                ))}
              </div>
            </div>
          )}
        </ReviewSection>

        <ReviewSection title="Sensors" icon={<Radio size={14} />}>
          {(data.sensors?.length || 0) === 0 ? (
            <p className="text-base text-muted-foreground py-2">No additional sensors configured.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {data.sensors?.map((s, i) => (
                <div key={i} className="flex flex-wrap gap-2 py-2 border-b border-border last:border-0">
                  <span className="text-base font-medium text-foreground">Sensor {i + 1}:</span>
                  <span className="text-sm bg-surface text-brand px-2.5 py-1 rounded-md border border-border">{s.sensor_type}</span>
                  <span className="text-sm bg-surface text-foreground px-2.5 py-1 rounded-md border border-border">{s.mounting_location}</span>
                  <span className="text-sm bg-surface text-foreground px-2.5 py-1 rounded-md border border-border">{s.orientation}</span>
                </div>
              ))}
            </div>
          )}
        </ReviewSection>
      </div>

      <SectionCard title="Asset Configuration" icon={<ClipboardCheck size={16} />}>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-base font-medium text-foreground">Asset Status</label>
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
              className="w-4 h-4 text-brand rounded border-border focus:ring-[rgba(245,166,35,0.15)]"
              {...register("machine_train_configured")}
            />
            <label htmlFor="machine_train_configured" className="text-base text-foreground">
              Machine Train Configured
            </label>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="bearing_database_mapped"
              className="w-4 h-4 text-brand rounded border-border focus:ring-[rgba(245,166,35,0.15)]"
              {...register("bearing_database_mapped")}
            />
            <label htmlFor="bearing_database_mapped" className="text-base text-foreground">
              Bearing Database Mapped
            </label>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="operating_mode_configured"
              className="w-4 h-4 text-brand rounded border-border focus:ring-[rgba(245,166,35,0.15)]"
              {...register("operating_mode_configured")}
            />
            <label htmlFor="operating_mode_configured" className="text-base text-foreground">
              Operating Mode Configured
            </label>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
