import React, { useState } from "react";
import { useFormContext, useFieldArray, Controller } from "react-hook-form";
import { Radio, Plus, Trash2 } from "lucide-react";
import { EquipmentFormData } from "@/types/equipment";
import { SectionCard } from "@/components/ui/SectionCard";
import { Button } from "@/components/ui/Button";
import { SelectInput, TextInput } from "@/components/ui/FormField";
import { SensorMountingDiagram } from "../SensorMountingDiagram";

const SENSOR_TYPES = [
  "IEPE Accelerometer", "MEMS Accelerometer", "Velocity Sensor", "Displacement Probe",
  "Eddy Current Probe", "Ultrasound Sensor", "Temperature Sensor", "RTD", "Thermocouple",
  "Pressure Sensor", "Current Sensor", "Flow Sensor", "Tachometer", "RPM Sensor",
];
const MOUNTING_LOCATIONS = [
  "Bearing Housing DE", "Bearing Housing NDE", "Motor DE", "Motor NDE",
  "Gearbox Input", "Gearbox Output", "Pump Casing", "Fan Housing",
  "Compressor Housing", "Foundation", "Custom",
];
const ORIENTATIONS = ["Horizontal", "Vertical", "Axial", "Radial", "Tangential"];
const MOUNTING_METHODS = [
  "Stud Mounted", "Magnetic Base", "Adhesive Mounted", "Handheld",
  "Threaded Mount", "Embedded", "Bracket Mounted", "Probe Holder", "Custom",
];
const SENSITIVITY_UNITS = ["mV/g", "mV/mm/s", "mV/µm", "mA", "V"];
const SAMPLING_RATES = ["512 Hz", "1024 Hz", "2048 Hz", "4096 Hz", "8192 Hz", "16384 Hz", "32768 Hz", "65536 Hz", "Custom"];
const FREQUENCY_RANGES = ["0-500 Hz", "0-1000 Hz", "0-2000 Hz", "0-5000 Hz", "0-10000 Hz", "0-20000 Hz", "Custom"];

const DEFAULT_SENSOR_ROWS = [
  { label: "DE Horizontal", location: "DE Horizontal", mountingLocation: "Bearing Housing DE", orientation: "Horizontal" },
  { label: "DE Vertical", location: "DE Vertical", mountingLocation: "Bearing Housing DE", orientation: "Vertical" },
  { label: "DE Axial", location: "DE Axial", mountingLocation: "Bearing Housing DE", orientation: "Axial" },
  { label: "NDE Horizontal", location: "NDE Horizontal", mountingLocation: "Bearing Housing NDE", orientation: "Horizontal" },
  { label: "NDE Vertical", location: "NDE Vertical", mountingLocation: "Bearing Housing NDE", orientation: "Vertical" },
  { label: "NDE Axial", location: "NDE Axial", mountingLocation: "Bearing Housing NDE", orientation: "Axial" },
];

export function SensorsOrientationTab() {
  const { control, watch, register } = useFormContext<EquipmentFormData>();
  const { fields, append, remove } = useFieldArray({ control, name: "sensors" });
  const sensors = watch("sensors") || [];

  const [defaultRows, setDefaultRows] = useState(
    DEFAULT_SENSOR_ROWS.map((r) => ({ ...r, selectedMounting: r.mountingLocation, selectedOrientation: r.orientation }))
  );

  const diagramOrientations: Record<string, string> = {};
  defaultRows.forEach((row) => {
    diagramOrientations[row.label] = row.selectedOrientation;
  });

  const addSensor = () => {
    append({
      sensor_type: "",
      mounting_location: "",
      orientation: "",
      mounting_method: undefined,
      sensitivity: undefined,
      sensitivity_unit: undefined,
      sampling_rate: undefined,
      sampling_rate_custom: undefined,
      frequency_range: undefined,
      frequency_range_custom_min: undefined,
      frequency_range_custom_max: undefined,
      is_active: true,
    });
  };

  return (
    <div className="flex flex-col gap-g5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-g5">
        <div className="lg:col-span-2">
          <SectionCard title="Sensor Mounting & Orientation" icon={<Radio size={16} />}>
            <div className="overflow-x-auto min-w-0">
              <table className="w-full text-base">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-lg font-semibold text-muted-foreground pb-4 pr-6">Location</th>
                    <th className="text-left text-lg font-semibold text-muted-foreground pb-4 pr-6">Mounting Location</th>
                    <th className="text-left text-lg font-semibold text-muted-foreground pb-4">Orientation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {defaultRows.map((row, idx) => (
                    <tr key={row.label} className="py-2">
                      <td className="py-2 pr-4">
                        <span className="text-lg font-semibold text-foreground">{row.label}</span>
                      </td>
                      <td className="py-2 pr-4">
                        <select
                          className="w-full text-base px-4 py-3 border border-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary/10"
                          value={row.selectedMounting}
                          onChange={(e) => {
                            const updated = [...defaultRows];
                            updated[idx] = { ...updated[idx], selectedMounting: e.target.value };
                            setDefaultRows(updated);
                          }}
                        >
                          {MOUNTING_LOCATIONS.map((loc) => (
                            <option key={loc} value={loc}>{loc}</option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2">
                        <select
                          className="w-full text-base px-4 py-3 border border-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary/10"
                          value={row.selectedOrientation}
                          onChange={(e) => {
                            const updated = [...defaultRows];
                            updated[idx] = { ...updated[idx], selectedOrientation: e.target.value };
                            setDefaultRows(updated);
                          }}
                        >
                          {ORIENTATIONS.map((o) => (
                            <option key={o} value={o}>{o}</option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>

        {/* Diagram */}
        <div className="bg-white rounded-xl border border-border shadow-sm p-5 flex items-center justify-center">
          <SensorMountingDiagram orientations={diagramOrientations} />
        </div>
      </div>

      {/* Additional Sensors */}
      <SectionCard scrollBody title="Additional Sensors" icon={<Radio size={16} />}>
        <div className="flex items-center justify-end mb-4">
          <Button type="button" size="sm" icon={<Plus size={14} />} onClick={addSensor}>
            Add Sensor
          </Button>
        </div>

        <div className="flex flex-col gap-4">
          {fields.map((field, idx) => {
            const samplingRate = watch(`sensors.${idx}.sampling_rate`);
            const freqRange = watch(`sensors.${idx}.frequency_range`);
            return (
              <div key={field.id} className="border border-border rounded-xl p-4 bg-white relative">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-lg font-semibold text-foreground">Sensor {idx + 1}</span>
                  <button
                    type="button"
                    onClick={() => remove(idx)}
                    className="text-destructive hover:text-destructive p-1 rounded hover:bg-destructive/10 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  {/* Sensor Type */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Sensor Type *</label>
                    <Controller
                      name={`sensors.${idx}.sensor_type`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} options={SENSOR_TYPES} placeholder="Select type" />
                      )}
                    />
                  </div>

                  {/* Mounting Location */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Mounting Location *</label>
                    <Controller
                      name={`sensors.${idx}.mounting_location`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} options={MOUNTING_LOCATIONS} placeholder="Select location" />
                      )}
                    />
                  </div>

                  {/* Orientation */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Orientation *</label>
                    <Controller
                      name={`sensors.${idx}.orientation`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} options={ORIENTATIONS} placeholder="Select orientation" />
                      )}
                    />
                  </div>

                  {/* Mounting Method */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Mounting Method</label>
                    <Controller
                      name={`sensors.${idx}.mounting_method`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} value={f.value || ""} options={MOUNTING_METHODS} placeholder="Select method" />
                      )}
                    />
                  </div>

                  {/* Sensitivity */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Sensitivity</label>
                    <div className="flex gap-1">
                      <input
                        type="number"
                        step="0.0001"
                        min="0"
                        {...register(`sensors.${idx}.sensitivity`)}
                        placeholder="Value"
                        className="flex-1 min-w-0 px-2 py-1.5 text-sm border border-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]/30"
                      />
                      <Controller
                        name={`sensors.${idx}.sensitivity_unit`}
                        control={control}
                        render={({ field: f }) => (
                          <select
                            {...f}
                            value={f.value || ""}
                            className="w-20 px-1 py-1.5 text-sm border border-border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]/30"
                          >
                            <option value="">Unit</option>
                            {SENSITIVITY_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                          </select>
                        )}
                      />
                    </div>
                  </div>

                  {/* Sampling Rate */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Sampling Rate</label>
                    <Controller
                      name={`sensors.${idx}.sampling_rate`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} value={f.value || ""} options={SAMPLING_RATES} placeholder="Select rate" />
                      )}
                    />
                    {samplingRate === "Custom" && (
                      <div className="flex items-center gap-1 mt-1">
                        <input
                          type="number"
                          min="1"
                          {...register(`sensors.${idx}.sampling_rate_custom`)}
                          placeholder="Hz value"
                          className="flex-1 px-2 py-1.5 text-sm border border-brand/30 rounded-lg bg-brand/5 focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]/30"
                        />
                        <span className="text-sm text-muted-foreground">Hz</span>
                      </div>
                    )}
                  </div>

                  {/* Frequency Range */}
                  <div className="flex flex-col gap-1">
                    <label className="text-lg font-semibold text-foreground">Frequency Range</label>
                    <Controller
                      name={`sensors.${idx}.frequency_range`}
                      control={control}
                      render={({ field: f }) => (
                        <SelectInput {...f} value={f.value || ""} options={FREQUENCY_RANGES} placeholder="Select range" />
                      )}
                    />
                    {freqRange === "Custom" && (
                      <div className="flex items-center gap-1 mt-1">
                        <input
                          type="number"
                          min="0"
                          {...register(`sensors.${idx}.frequency_range_custom_min`)}
                          placeholder="Min Hz"
                          className="flex-1 px-2 py-1.5 text-sm border border-brand/30 rounded-lg bg-brand/5 focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]/30"
                        />
                        <span className="text-sm text-muted-foreground">—</span>
                        <input
                          type="number"
                          min="0"
                          {...register(`sensors.${idx}.frequency_range_custom_max`)}
                          placeholder="Max Hz"
                          className="flex-1 px-2 py-1.5 text-sm border border-brand/30 rounded-lg bg-brand/5 focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.15)]/30"
                        />
                        <span className="text-sm text-muted-foreground">Hz</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}
