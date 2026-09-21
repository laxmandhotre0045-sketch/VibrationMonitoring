import React, { useCallback, useMemo, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Box, Info } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
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
  1: "Pick a Machine Type to load its model.",
  2: "Mechanical details refine the asset this twin represents.",
  3: "Bearings appear at their mounting positions as you enter them.",
  4: "Operating conditions apply to the asset shown here.",
  5: "Each mounting row and added sensor is placed and pointed below.",
  6: "Check the bearings and sensor positions before you save the layout.",
};

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

  const [highlightedId, setHighlightedId] = useState<string | null>(null);
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

  // A pin survives the pointer leaving; a hover wins while it is happening.
  const effectiveHighlight = highlightedId ?? pinnedId;

  const handleSelect = useCallback((id: string) => {
    setPinnedId((current) => (current === id ? null : id));
  }, []);

  const isReview = activeStep === 6;

  return (
    <div className={cn("content-card card-auto", cardHover.soft, className)}>
      <div className="card-pad pb-0">
        <div className="flex min-w-0 items-center gap-g2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FFA500]/10 orange-gradient-border text-[#FFA500]">
            <Box size={15} />
          </span>
          <div className="min-w-0">
            <h3 className="text-section-title">3D Digital Twin</h3>
            <p className="text-helper mt-g1">
              {twin.machineTypeLabel || "No machine type selected"}
              {twin.machineName && (
                <span className="text-muted-foreground"> · {twin.machineName}</span>
              )}
              {" — "}
              {STEP_CAPTION[activeStep] ?? STEP_CAPTION[1]}
            </p>
          </div>
        </div>
      </div>

      <div className="card-pad pt-g3">
        <div
          className={cn(
            "grid gap-g4",
            // The list sits beside the model from lg up, and underneath it on
            // narrower screens rather than being hidden — it is the readable
            // version of what the 3D view shows.
            isReview
              ? "grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px]"
              : "grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px]"
          )}
        >
          <div className="min-w-0">
            <React.Suspense
              fallback={
                <div className="h-[316px] w-full animate-pulse rounded-lg border border-border bg-surface sm:h-[396px] xl:h-[476px]" />
              }
            >
              <DigitalTwinViewer
                machineType={twin.machineType}
                bearings={twin.bearings}
                sensors={twin.sensors}
                highlightedId={effectiveHighlight}
                onHighlight={setHighlightedId}
                onSelect={handleSelect}
              />
            </React.Suspense>

            {twin.machineType === "generic" && (
              <p className="mt-g2 flex items-start gap-1.5 text-xs text-muted-foreground">
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
            highlightedId={effectiveHighlight}
            onHighlight={setHighlightedId}
            onSelect={handleSelect}
            className="min-w-0"
          />
        </div>
      </div>
    </div>
  );
}
