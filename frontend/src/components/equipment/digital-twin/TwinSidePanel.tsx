import React from "react";
import type { TwinBearing, TwinSensor } from "@/lib/digital-twin/types";
import { cn } from "@/lib/utils";

interface TwinSidePanelProps {
  bearings: TwinBearing[];
  sensors: TwinSensor[];
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onSelect: (id: string) => void;
  className?: string;
}

const STATUS_DOT: Record<string, string> = {
  ok: "bg-machine-healthy",
  alert: "bg-machine-warning",
  danger: "bg-machine-critical",
};

/**
 * One row. A real `<button>` so it is tabbable, has a visible focus ring and
 * activates on Enter and Space without any key handling of our own.
 *
 * Hover and focus both drive `onHighlight`, which is what makes pointing at a
 * row light up its marker in 3D — and, because the parent owns
 * `highlightedId`, pointing at the marker light up the row.
 */
function Row({
  id,
  lead,
  title,
  detail,
  statusDot,
  muted,
  highlighted,
  onHighlight,
  onSelect,
}: {
  id: string;
  lead: string;
  title: string;
  detail: string;
  statusDot?: string;
  muted?: boolean;
  highlighted: boolean;
  onHighlight: (id: string | null) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onMouseEnter={() => onHighlight(id)}
      onMouseLeave={() => onHighlight(null)}
      onFocus={() => onHighlight(id)}
      onBlur={() => onHighlight(null)}
      onClick={() => onSelect(id)}
      className={cn(
        "w-full rounded-lg border px-g3 py-g2 text-left transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60",
        highlighted
          ? "border-[#FF6B00] bg-[#FF6B00]/10"
          : "border-border bg-white hover:border-[#FF6B00]/40"
      )}
    >
      <span className="flex flex-wrap items-baseline gap-x-1.5">
        {statusDot && (
          <span className={cn("h-2 w-2 shrink-0 self-center rounded-full", statusDot)} aria-hidden />
        )}
        <span className="text-sm font-bold text-[#FF6B00]">{lead}</span>
        <span
          className={cn(
            "text-sm font-semibold",
            muted ? "text-muted-foreground" : "text-foreground"
          )}
        >
          {title}
        </span>
      </span>
      <span className="mt-0.5 block text-xs text-muted-foreground">{detail}</span>
    </button>
  );
}

function Legend() {
  const items = [
    { color: "#FF6B00", label: "Sensor channel" },
    { color: "#F5A623", label: "Configured bearing" },
    { color: "#BCC7D6", label: "Bearing not configured" },
  ];
  return (
    <div className="flex flex-wrap gap-x-g3 gap-y-1 border-t border-border pt-g3">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: item.color }}
            aria-hidden
          />
          <span className="text-xs text-muted-foreground">{item.label}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * The bearings and sensors list beside the 3D view.
 *
 * Deliberately a dumb list: it holds no selection state of its own, so it can
 * never disagree with the 3D view about what is highlighted.
 */
export function TwinSidePanel({
  bearings,
  sensors,
  highlightedId,
  onHighlight,
  onSelect,
  className,
}: TwinSidePanelProps) {
  return (
    <div className={cn("flex flex-col gap-g3", className)}>
      <div>
        <p className="text-overline mb-g2">Bearings, {bearings.length} positions</p>
        {bearings.length === 0 ? (
          <p className="text-helper">This model has no bearing positions.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {bearings.map((bearing, index) => (
              <Row
                key={bearing.id}
                id={bearing.id}
                lead={`B${index + 1}`}
                title={bearing.name}
                detail={
                  bearing.configured
                    ? bearing.note ?? "Configured"
                    : "Not configured"
                }
                muted={!bearing.configured}
                highlighted={highlightedId === bearing.id}
                onHighlight={onHighlight}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="text-overline mb-g2">
          Sensors, {sensors.length} point{sensors.length === 1 ? "" : "s"}
        </p>
        {sensors.length === 0 ? (
          <p className="text-helper">No sensor mounting configured.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {sensors.map((sensor) => (
              <Row
                key={sensor.id}
                id={sensor.id}
                lead={sensor.id}
                title={`${sensor.location}, ${sensor.axis.toLowerCase()}`}
                detail={
                  sensor.persisted
                    ? sensor.detail ?? "Additional sensor"
                    : "Standard mounting point"
                }
                statusDot={sensor.status ? STATUS_DOT[sensor.status] : undefined}
                highlighted={highlightedId === sensor.id}
                onHighlight={onHighlight}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </div>

      <Legend />
    </div>
  );
}
