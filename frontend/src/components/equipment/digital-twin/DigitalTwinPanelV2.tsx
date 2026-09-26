import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Box, Info } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
import type { TwinSensorPlacement } from "@/lib/digital-twin/types";
import { adaptEquipmentToTwin } from "@/lib/digital-twin/adapt-equipment";
import { twinSignature } from "@/lib/digital-twin/twin-config";
import { TwinSidePanel } from "./TwinSidePanel";
import { toMountingRowInputs, useMountingRows } from "./DigitalTwinContext";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

/**
 * three.js is the only heavy dependency this feature adds and it is reachable
 * from one page, so the viewer is split out of the main bundle — the same
 * treatment the advanced analysis plots already get.
 */
const DigitalTwinViewer = React.lazy(() =>
  import("./DigitalTwinViewerV2").then((m) => ({ default: m.DigitalTwinViewer }))
);

interface DigitalTwinPanelV2Props {
  /** Drives the caption only — one viewer serves every step. */
  activeStep: number;
  equipmentId?: string;
  className?: string;
}

const STEP_CAPTION: Record<number, string> = {
  1: "Pick a Machine Type in Step 1 to load its model.",
  2: "Mechanical details refine the asset shown here.",
  3: "Bearings appear at their mounting positions as you enter them.",
  4: "Operating conditions apply to the asset shown here.",
  5: "Each mounting row and added sensor is placed and pointed below.",
  6: "Check the bearings and sensor positions before you save the layout.",
};

/** A compact count, so the header says what the model is carrying at a glance. */
function HeaderStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-end leading-none">
      <span className="text-sm font-bold tabular-nums text-foreground">{value}</span>
      <span className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

/**
 * The 3D Digital Twin step.
 *
 * Owns `highlightedId` so the side panel and the 3D view can never disagree
 * about what is highlighted — hovering a row lights the marker, hovering the
 * marker lights the row, and both go through the same piece of state.
 */
export function DigitalTwinPanelV2({
  activeStep,
  equipmentId,
  className,
}: DigitalTwinPanelV2Props) {
  const { watch } = useFormContext<EquipmentFormData>();
  const data = watch();
  const { rows } = useMountingRows();

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [pinnedId, setPinnedId] = useState<string | null>(null);

  const mountingRows = useMemo(() => toMountingRowInputs(rows), [rows]);
  // `watch()` returns a fresh object on every keystroke in any of some sixty
  // fields. Keying on a signature of just the fields the twin draws from stops
  // the scene being rebuilt while someone types a serial number.
  const signature = twinSignature(data, mountingRows);
  const twin = useMemo(
    () => adaptEquipmentToTwin(data, mountingRows),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [signature]
  );

  /**
   * Sensors dragged off their anchor onto a point of the operator's choosing.
   *
   * Held here rather than in the form: `sensor_configurations` has no column
   * for a mounting coordinate, so there is nowhere to save one yet. These
   * survive edits to the rest of the form and are lost when the page is left.
   *
   * Keyed by what the sensor *is*, not by its channel. A channel is positional
   * — delete the second mounting row and CH3 becomes CH2 — so keying by id
   * would quietly move one sensor's placement onto a different sensor.
   */
  const [placementsByKey, setPlacementsByKey] = useState<
    Record<string, TwinSensorPlacement>
  >({});

  const keyById = useMemo(() => {
    const occurrences = new Map<string, number>();
    const keys = new Map<string, string>();
    for (const sensor of twin.sensors) {
      const base = `${sensor.location}|${sensor.axis}|${sensor.detail ?? ""}`;
      const seen = occurrences.get(base) ?? 0;
      occurrences.set(base, seen + 1);
      keys.set(sensor.id, seen === 0 ? base : `${base}#${seen}`);
    }
    return keys;
  }, [twin.sensors]);

  const placements = useMemo(() => {
    const byId: Record<string, TwinSensorPlacement> = {};
    keyById.forEach((key, id) => {
      const placement = placementsByKey[key];
      if (placement) byId[id] = placement;
    });
    return byId;
  }, [keyById, placementsByKey]);

  const handlePlaceSensor = useCallback(
    (id: string, placement: TwinSensorPlacement | null) => {
      const key = keyById.get(id);
      if (!key) return;
      setPlacementsByKey((current) => {
        if (!placement) {
          if (!(key in current)) return current;
          const { [key]: _removed, ...rest } = current;
          return rest;
        }
        return { ...current, [key]: placement };
      });
    },
    [keyById]
  );

  // A placement is a point on one specific model. Changing the Machine Type
  // swaps the geometry under it, so the old points stop meaning anything.
  useEffect(() => {
    setPlacementsByKey({});
  }, [twin.machineType]);

  // A pin survives the pointer leaving; a hover wins while it is happening.
  const highlightedId = hoveredId ?? pinnedId;

  const handleSelect = useCallback((id: string) => {
    setPinnedId((current) => (current === id ? null : id));
  }, []);

  // Escape releases a pinned selection — the pin is the only sticky state in
  // this panel, so it needs an obvious way out that is not "click it again".
  useEffect(() => {
    if (!pinnedId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPinnedId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pinnedId]);

  const configuredBearings = twin.bearings.filter((bearing) => bearing.configured).length;

  return (
    <div className={cn("content-card card-auto", cardHover.soft, className)}>
      <div className="card-pad pb-0">
        <div className="flex flex-wrap items-start justify-between gap-g3">
          <div className="flex min-w-0 items-center gap-g2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FFA500]/10 orange-gradient-border text-[#FFA500]">
              <Box size={15} />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-g2">
                <h3 className="text-section-title">3D Digital Twin</h3>
                {twin.machineTypeLabel && (
                  <span className="rounded-full border border-border bg-surface px-2 py-px text-[11px] font-semibold text-foreground">
                    {twin.machineTypeLabel}
                  </span>
                )}
              </div>
              <p className="text-helper mt-g1">
                {twin.machineName && (
                  <span className="font-medium text-foreground">{twin.machineName} — </span>
                )}
                {STEP_CAPTION[activeStep] ?? STEP_CAPTION[1]}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-g3">
            <HeaderStat
              value={`${configuredBearings}/${twin.bearings.length}`}
              label="Bearings"
            />
            <span className="h-7 w-px bg-border" aria-hidden />
            <HeaderStat value={String(twin.sensors.length)} label="Sensors" />
          </div>
        </div>
      </div>

      <div className="card-pad pt-g3">
        {/* The list sits beside the model from lg up and underneath it below —
            it is the readable version of what the 3D view shows, never hidden.
            `items-start` plus a cap on the list keeps the two columns roughly
            level: left to itself the list is taller than the viewer and leaves
            a block of dead space under the stage. */}
        <div className="grid grid-cols-1 items-start gap-g4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
            <React.Suspense
              fallback={
                <div className="h-[356px] w-full animate-pulse rounded-xl border border-border bg-surface sm:h-[436px] xl:h-[516px]" />
              }
            >
              <DigitalTwinViewer
                machineType={twin.machineType}
                bearings={twin.bearings}
                sensors={twin.sensors}
                highlightedId={highlightedId}
                onHighlight={setHoveredId}
                onSelect={handleSelect}
                placements={placements}
                onPlaceSensor={handlePlaceSensor}
              />
            </React.Suspense>

            {twin.machineType === "generic" && (
              <p className="mt-g2 flex items-start gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-muted-foreground">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>
                  {twin.machineTypeLabel
                    ? `No dedicated model for "${twin.machineTypeLabel}" yet — showing a generic rotating machine with drive and non-drive ends.`
                    : "Showing a generic rotating machine until a Machine Type is selected in Step 1."}
                </span>
              </p>
            )}
          </div>

          <TwinSidePanel
            bearings={twin.bearings}
            sensors={twin.sensors}
            highlightedId={highlightedId}
            onHighlight={setHoveredId}
            onSelect={handleSelect}
            // Matches the viewer column: toolbar + stage + hint at each
            // breakpoint. Anything past that scrolls inside the list.
            className="min-w-0 lg:max-h-[448px] xl:max-h-[528px]"
          />
        </div>
      </div>
    </div>
  );
}
