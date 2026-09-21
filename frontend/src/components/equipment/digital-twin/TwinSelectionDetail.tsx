import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, X } from "lucide-react";
import { getBearing } from "@/api/bearings";
import type { ResolvedBearing, ResolvedSensor } from "@/lib/digital-twin/types";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface TwinSelectionDetailProps {
  bearing: ResolvedBearing | null;
  sensor: ResolvedSensor | null;
  /** Set once the equipment exists, which is what makes analysis reachable. */
  equipmentId?: string;
  onClose: () => void;
  className?: string;
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-g2 py-1">
      <span className="w-24 shrink-0 text-xs font-medium text-muted-foreground">{label}</span>
      <span className="min-w-0 text-sm font-semibold text-foreground break-words">{value}</span>
    </div>
  );
}

/**
 * The bearing's catalogued defect frequencies.
 *
 * Read straight from the existing bearing catalogue endpoint under the same
 * query key the Step 3 field uses, so it is usually already cached and no
 * frequency is ever recomputed here — the diagnostic maths stays in one place.
 */
function BearingFrequencies({ catalogId }: { catalogId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["bearing", catalogId],
    queryFn: () => getBearing(catalogId),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return <p className="text-xs text-muted-foreground">Loading catalogue…</p>;
  }
  if (!data) return null;

  const values = [
    { label: "FTF", value: data.ftf },
    { label: "BSF", value: data.bsf },
    { label: "BPFO", value: data.bpfo },
    { label: "BPFI", value: data.bpfi },
  ];

  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
        Defect frequencies · orders of running speed
      </p>
      <div className="mt-1.5 grid grid-cols-4 gap-1.5">
        {values.map((item) => (
          <div key={item.label} className="rounded-md border border-border bg-white px-1.5 py-1">
            <p className="text-[10px] font-bold uppercase leading-none text-muted-foreground">
              {item.label}
            </p>
            <p className="mt-0.5 text-xs font-bold tabular-nums leading-tight text-foreground">
              {item.value.toFixed(3)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * What a click in the 3D scene opens.
 *
 * Kept as ordinary HTML beside the canvas rather than an overlay inside it, so
 * it reads at any width, is selectable, and stays reachable by keyboard.
 */
export function TwinSelectionDetail({
  bearing,
  sensor,
  equipmentId,
  onClose,
  className,
}: TwinSelectionDetailProps) {
  const navigate = useNavigate();
  if (!bearing && !sensor) return null;

  return (
    <div
      className={cn(
        "rounded-lg border border-[#FF6B00]/30 bg-[#FFF8F2] px-g3 py-g3",
        className
      )}
    >
      <div className="flex items-start justify-between gap-g2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#FF6B00]">
            {bearing ? "Bearing" : "Sensor"}
          </p>
          <p className="text-base font-bold text-foreground truncate">
            {bearing
              ? `${bearing.position} · ${bearing.bearingNumber || "Catalogue match"}`
              : `${sensor!.channel} — ${sensor!.rowLabel}`}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close details"
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-black/5 hover:text-foreground"
        >
          <X size={14} />
        </button>
      </div>

      <div className="mt-g2">
        {bearing ? (
          <>
            <DetailRow label="Position" value={bearing.anchor.label} />
            {bearing.bearingNumber && (
              <DetailRow label="Bearing no." value={bearing.bearingNumber} />
            )}
            <DetailRow
              label="Catalogue"
              value={
                bearing.catalogId
                  ? `Bearing ID ${bearing.catalogId}`
                  : "Free text — not matched to the catalogue"
              }
            />
            {bearing.catalogId && (
              <div className="mt-g2">
                <BearingFrequencies catalogId={bearing.catalogId} />
              </div>
            )}
          </>
        ) : (
          <>
            <DetailRow label="Location" value={sensor!.mountingLocation} />
            <DetailRow label="Orientation" value={sensor!.orientation} />
            {sensor!.sensorType && <DetailRow label="Type" value={sensor!.sensorType} />}
            <DetailRow label="Anchor" value={sensor!.anchor.label} />
            <DetailRow
              label="Status"
              value={
                sensor!.source === "sensor"
                  ? "Sensor configured — saved with the equipment"
                  : "Standard mounting point — reference only, not saved as a sensor"
              }
            />
            {!sensor!.mapped && (
              <p className="mt-g2 rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                A {twinModelNoun(sensor!.mountingLocation)} is not part of the selected machine
                type's model, so this marker sits on the foundation. The saved configuration is
                unaffected.
              </p>
            )}

            {/* Only reachable once the equipment exists — during creation there
                is nothing for the analysis page to load yet. */}
            {equipmentId && sensor!.source === "sensor" && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="mt-g2 w-full"
                icon={<ArrowUpRight size={13} />}
                onClick={() =>
                  navigate(
                    `/analysis?equipmentId=${encodeURIComponent(equipmentId)}` +
                      `&mountingLocation=${encodeURIComponent(sensor!.mountingLocation)}` +
                      `&orientation=${encodeURIComponent(sensor!.orientation)}`
                  )
                }
              >
                View Analysis
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** "Pump Casing" → "pump casing", for use mid-sentence. */
function twinModelNoun(mountingLocation: string): string {
  return mountingLocation.toLowerCase();
}
