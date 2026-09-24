import React from "react";
import { Radio, RotateCw } from "lucide-react";
import type { TwinBearing, TwinSensor } from "@/lib/digital-twin/types";
import { cn } from "@/lib/utils";

interface TwinSidePanelProps {
  bearings: TwinBearing[];
  sensors: TwinSensor[];
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onSelect: (id: string) => void;
  /** Kept in step with the stage height so the card never grows past it. */
  className?: string;
}

const STATUS_DOT: Record<string, string> = {
  ok: "bg-machine-healthy",
  alert: "bg-machine-warning",
  danger: "bg-machine-critical",
};

/**
 * One row.
 *
 * A real `<button>`, so it is tabbable, has a visible focus ring and activates
 * on Enter and Space with no key handling of our own. Hover *and* focus drive
 * `onHighlight`, which is what makes pointing at a row light up its marker in
 * 3D — and, because the parent owns `highlightedId`, pointing at the marker
 * light up the row.
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
        "group relative w-full rounded-lg border px-g3 py-2 text-left transition-all duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60",
        highlighted
          ? "border-[#FF6B00] bg-[#FF6B00]/[0.07] shadow-sm"
          : "border-border bg-white hover:border-[#FF6B00]/40 hover:bg-[#FF6B00]/[0.03]"
      )}
    >
      {/* A rail rather than a border change, so the row does not shift by a
          pixel when it lights up. */}
      <span
        aria-hidden
        className={cn(
          "absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full transition-colors",
          highlighted ? "bg-[#FF6B00]" : "bg-transparent"
        )}
      />
      <span className="flex flex-wrap items-baseline gap-x-1.5">
        {statusDot && (
          <span
            className={cn("h-2 w-2 shrink-0 self-center rounded-full", statusDot)}
            aria-hidden
          />
        )}
        <span
          className={cn(
            "text-sm font-bold tabular-nums",
            muted ? "text-muted-foreground" : "text-[#FF6B00]"
          )}
        >
          {lead}
        </span>
        <span
          className={cn(
            "text-sm font-semibold leading-snug",
            muted ? "text-muted-foreground" : "text-foreground"
          )}
        >
          {title}
        </span>
      </span>
      <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">{detail}</span>
    </button>
  );
}

function SectionHeading({
  icon,
  title,
  count,
  note,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  note?: string;
}) {
  return (
    <div className="mb-g2 flex items-baseline justify-between gap-g2">
      <span className="flex items-center gap-1.5">
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-overline">{title}</span>
        <span className="rounded-full bg-surface px-1.5 py-px text-[10px] font-bold tabular-nums text-muted-foreground">
          {count}
        </span>
      </span>
      {note && <span className="text-[11px] text-muted-foreground">{note}</span>}
    </div>
  );
}

function Legend() {
  const items = [
    { color: "#FF6B00", label: "Sensor channel" },
    { color: "#F5A623", label: "Configured bearing" },
    { color: "#BCC7D6", label: "Not configured" },
  ];
  return (
    <div className="flex flex-wrap gap-x-g3 gap-y-1 border-t border-border pt-g2">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: item.color }}
            aria-hidden
          />
          <span className="text-[11px] text-muted-foreground">{item.label}</span>
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
  const configured = bearings.filter((bearing) => bearing.configured).length;

  return (
    <div className={cn("flex min-h-0 flex-col gap-g3", className)}>
      {/* The lists scroll inside the panel rather than stretching the card, so
          a machine with a dozen sensors keeps the 3D view the same height. The
          fade at the bottom is the only cue that there is more below — a thin
          scrollbar alone reads as a cut-off list. */}
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-g3 overflow-y-auto pr-0.5 scrollbar-thin">
        <div>
          <SectionHeading
            icon={<RotateCw size={12} />}
            title="Bearings"
            count={bearings.length}
            note={
              bearings.length > 0
                ? `${configured} configured`
                : undefined
            }
          />
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
                  detail={bearing.configured ? bearing.note ?? "Configured" : "Not configured"}
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
          <SectionHeading icon={<Radio size={12} />} title="Sensors" count={sensors.length} />
          {sensors.length === 0 ? (
            <p className="text-helper">
              No sensor mounting configured. Step 5 places each mounting row on the model.
            </p>
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
        </div>
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-white via-white/70 to-transparent"
        />
      </div>

      <Legend />
    </div>
  );
}
