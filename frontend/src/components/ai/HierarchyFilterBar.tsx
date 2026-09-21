import React, { useMemo } from "react";
import { ChevronDown } from "lucide-react";
import {
  hierarchyOptions,
  type HierarchyLevel,
  type HierarchySelection,
  type SensorHierarchy,
} from "@/lib/sensor-hierarchy";
import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  value: string;
  placeholder: string;
  disabled: boolean;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}

/**
 * One outlined select with its label notched into the border.
 *
 * The five of them read as a single path across the row, which a stack of
 * label-above-control fields does not — the eye has to pair each label with its
 * box again at every level.
 */
function HierarchyField({
  label,
  value,
  placeholder,
  disabled,
  options,
  onChange,
}: FieldProps) {
  return (
    <div
      className={cn(
        "relative rounded-lg border bg-white transition-colors",
        disabled
          ? "border-border opacity-60"
          : value
            ? "border-signal-light shadow-[0_0_0_1px_rgba(245,166,35,0.18)]"
            : "border-border hover:border-signal-light/55"
      )}
    >
      <span
        className={cn(
          "absolute -top-2 left-2.5 bg-white px-1 text-[10px] font-bold uppercase tracking-wide",
          value && !disabled ? "text-signal-dark" : "text-muted-foreground"
        )}
      >
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className={cn(
          "w-full cursor-pointer appearance-none bg-transparent py-2.5 pl-3 pr-8",
          "text-sm font-semibold text-foreground outline-none",
          "disabled:cursor-not-allowed"
        )}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={15}
        aria-hidden
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}

interface HierarchyFilterBarProps {
  hierarchy: SensorHierarchy;
  selection: HierarchySelection;
  onSelect: (level: HierarchyLevel, value: string) => void;
}

/**
 * Plant → Area → Line → Machine → Sensor, each level offering only what the
 * level above it contains.
 */
export function HierarchyFilterBar({
  hierarchy,
  selection,
  onSelect,
}: HierarchyFilterBarProps) {
  const options = useMemo(
    () => hierarchyOptions(hierarchy, selection),
    [hierarchy, selection]
  );

  const counts = hierarchy.counts;

  return (
    <div className="space-y-g3">
      <div className="grid grid-cols-1 gap-g3 sm:grid-cols-2 xl:grid-cols-5">
        <HierarchyField
          label="Plant"
          value={selection.plant}
          placeholder="Select plant"
          disabled={!options.plants.length}
          options={options.plants.map((p) => ({ value: p.label, label: p.label }))}
          onChange={(value) => onSelect("plant", value)}
        />
        <HierarchyField
          label="Area"
          value={selection.area}
          placeholder={selection.plant ? "Select area" : "Select a plant first"}
          disabled={!selection.plant}
          options={options.areas.map((a) => ({ value: a.label, label: a.label }))}
          onChange={(value) => onSelect("area", value)}
        />
        <HierarchyField
          label="Line"
          value={selection.line}
          placeholder={selection.area ? "Select line" : "Select an area first"}
          disabled={!selection.area}
          options={options.lines.map((l) => ({ value: l.label, label: l.label }))}
          onChange={(value) => onSelect("line", value)}
        />
        <HierarchyField
          label="Machine"
          value={selection.machineId}
          placeholder={selection.line ? "Select machine" : "Select a line first"}
          disabled={!selection.line}
          options={options.machines.map((m) => ({
            value: m.id,
            label: m.machineId ? `${m.label} — ${m.machineId}` : m.label,
          }))}
          onChange={(value) => onSelect("machine", value)}
        />
        <HierarchyField
          label="Sensor"
          value={selection.sensorId}
          placeholder={selection.machineId ? "Select sensor" : "Select a machine first"}
          disabled={!selection.machineId}
          options={options.sensors.map((s) => ({ value: s.id, label: s.label }))}
          onChange={(value) => onSelect("sensor", value)}
        />
      </div>

      <div className="flex flex-wrap items-center gap-g2">
        {(
          [
            ["Plants", counts.plants],
            ["Areas", counts.areas],
            ["Lines", counts.lines],
            ["Machines", counts.machines],
            ["Sensors", counts.sensors],
          ] as const
        ).map(([label, count]) => (
          <span
            key={label}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
              label === "Sensors"
                ? "border-signal-light/45 bg-signal-light/10 text-signal-deep"
                : "border-border bg-white text-muted-foreground"
            )}
          >
            {label}: {count}
          </span>
        ))}
      </div>
    </div>
  );
}
