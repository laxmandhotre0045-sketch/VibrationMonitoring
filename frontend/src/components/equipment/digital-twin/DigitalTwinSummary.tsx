import React from "react";
import type { ResolvedTwin } from "@/lib/digital-twin/types";
import { cn } from "@/lib/utils";

interface DigitalTwinSummaryProps {
  twin: ResolvedTwin;
  /** Highlighted row, kept in step with the 3D selection. */
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  className?: string;
}

function SummaryHeading({ children }: { children: React.ReactNode }) {
  return <p className="text-overline mb-g2">{children}</p>;
}

/**
 * The written-out configuration, beside the model.
 *
 * Step 6 is the last chance to catch a sensor pointing the wrong way, and a
 * list is easier to check line by line than a 3D view — so the two are shown
 * together and select each other.
 */
export function DigitalTwinSummary({
  twin,
  selectedKey,
  onSelect,
  className,
}: DigitalTwinSummaryProps) {
  const rowClass = (key: string) =>
    cn(
      "w-full text-left rounded-md border px-g2 py-1.5 transition-colors",
      selectedKey === key
        ? "border-[#FF6B00] bg-[#FF6B00]/10"
        : "border-border bg-white hover:border-[#FF6B00]/40"
    );

  return (
    <div className={cn("flex flex-col gap-g4", className)}>
      <div>
        <SummaryHeading>Bearings</SummaryHeading>
        {twin.bearings.length === 0 ? (
          <p className="text-helper">
            No bearing configured. Bearing details are optional — the equipment saves without
            them, and bearing-frequency diagnostics stay unavailable until one is added.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {twin.bearings.map((bearing) => (
              <button
                key={bearing.key}
                type="button"
                onClick={() => onSelect(selectedKey === bearing.key ? null : bearing.key)}
                className={rowClass(bearing.key)}
              >
                <span className="text-sm font-bold text-foreground">{bearing.position}</span>
                <span className="text-sm text-muted-foreground"> · {bearing.anchor.label}</span>
                <span className="block text-sm font-semibold text-[#D98C00]">
                  {bearing.bearingNumber || `Bearing ID ${bearing.catalogId}`}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <SummaryHeading>
          Sensors · {twin.sensors.length} point{twin.sensors.length === 1 ? "" : "s"}
        </SummaryHeading>
        {twin.sensors.length === 0 ? (
          <p className="text-helper">No sensor mounting configured.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {twin.sensors.map((sensor) => (
              <button
                key={sensor.key}
                type="button"
                onClick={() => onSelect(selectedKey === sensor.key ? null : sensor.key)}
                className={rowClass(sensor.key)}
              >
                <span className="flex flex-wrap items-baseline gap-x-1.5">
                  <span className="text-sm font-bold text-[#FF6B00]">{sensor.channel}</span>
                  <span className="text-sm font-semibold text-foreground">
                    {sensor.mountingLocation}
                  </span>
                  <span className="text-sm text-muted-foreground">— {sensor.orientation}</span>
                </span>
                <span className="block text-xs text-muted-foreground">
                  {sensor.source === "sensor"
                    ? sensor.sensorType || "Additional sensor"
                    : "Standard mounting point"}
                  {!sensor.mapped && " · shown on foundation"}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
