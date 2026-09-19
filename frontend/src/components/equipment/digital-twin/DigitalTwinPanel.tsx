import React, { useCallback, useMemo, useState } from "react";
import { useFormContext } from "react-hook-form";
import { Box, Info } from "lucide-react";
import type { EquipmentFormData } from "@/types/equipment";
import type { TwinPick } from "@/lib/digital-twin/types";
import { resolveTwin, twinSignature } from "@/lib/digital-twin/twin-config";
import { MachineIllustration } from "../MachineVisualizationPanel";
import { DigitalTwinControls } from "./DigitalTwinControls";
import { DigitalTwinSummary } from "./DigitalTwinSummary";
import { TwinSelectionDetail } from "./TwinSelectionDetail";
import { toMountingRowInputs, useMountingRows } from "./DigitalTwinContext";
import type { CameraViewId } from "./twin-scene";
import { cardHover } from "@/lib/card-hover";
import { cn } from "@/lib/utils";

/**
 * three.js is the only heavy dependency this feature adds, and it is reachable
 * from one page. Splitting the viewer out keeps it off the main bundle — the
 * same treatment the advanced analysis plots already get.
 *
 * `twin-scene` is imported for types only elsewhere, so this is the single
 * runtime entry point into three.
 */
const DigitalTwinViewer = React.lazy(() =>
  import("./DigitalTwinViewer").then((m) => ({ default: m.DigitalTwinViewer }))
);

interface DigitalTwinPanelProps {
  /** Drives the caption only — one viewer serves every step. */
  activeStep: number;
  /** Present when editing; enables the link through to vibration analysis. */
  equipmentId?: string;
  className?: string;
}

/** What the twin is showing the operator on each step. */
const STEP_CAPTION: Record<number, string> = {
  1: "Pick a Machine Type to load its model.",
  2: "Mechanical details refine the asset this twin represents.",
  3: "Bearings appear at their mounting positions as you enter them.",
  4: "Operating conditions apply to the asset shown here.",
  5: "Each mounting row and added sensor is placed and pointed below.",
  6: "Confirm the machine, bearings and sensor layout before saving.",
};

function Legend() {
  const items = [
    { color: "#FF6B00", label: "Sensor / channel" },
    { color: "#F5A623", label: "Configured bearing" },
    { color: "#BCC7D6", label: "Bearing position — not configured" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-g3 gap-y-1">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          <span className="text-xs text-muted-foreground">{item.label}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * The interactive 3D Digital Twin.
 *
 * Mounted **once** for the whole form rather than once per step: the six step
 * panels all stay mounted behind `display:none`, so a viewer inside each would
 * mean four live WebGL contexts for one machine. One panel below the step body
 * also means the twin is visible at every breakpoint, including the ones where
 * the xl-only intelligence sidebar is hidden.
 */
export function DigitalTwinPanel({ activeStep, equipmentId, className }: DigitalTwinPanelProps) {
  const { watch } = useFormContext<EquipmentFormData>();
  const data = watch();
  const { rows } = useMountingRows();

  const [selected, setSelected] = useState<TwinPick | null>(null);
  const [view, setView] = useState<{ view: CameraViewId; nonce: number }>({
    view: "iso",
    nonce: 0,
  });

  const mountingRows = useMemo(() => toMountingRowInputs(rows), [rows]);
  // `watch()` returns a fresh object on every keystroke in any of ~60 fields.
  // Keying the twin on a signature of just the fields it draws from keeps the
  // scene from being rebuilt while someone types a serial number.
  const signature = twinSignature(data, mountingRows);
  const twin = useMemo(
    () => resolveTwin(data, mountingRows),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [signature]
  );

  const selectView = useCallback((next: CameraViewId) => {
    setView((current) => ({ view: next, nonce: current.nonce + 1 }));
  }, []);

  const selectedKey = selected?.key ?? null;
  const selectedBearing =
    selected?.kind === "bearing"
      ? twin.bearings.find((bearing) => bearing.key === selected.key) ?? null
      : null;
  const selectedSensor =
    selected?.kind === "sensor"
      ? twin.sensors.find((sensor) => sensor.key === selected.key) ?? null
      : null;

  // A marker can disappear underneath the selection — a sensor row removed, a
  // bearing number cleared. Drop the stale detail rather than showing nothing.
  const activeSelection = selectedBearing || selectedSensor ? selected : null;

  const selectByKey = useCallback(
    (key: string | null) => {
      if (key === null) {
        setSelected(null);
        return;
      }
      const bearing = twin.bearings.find((item) => item.key === key);
      setSelected(bearing ? { kind: "bearing", key } : { kind: "sensor", key });
    },
    [twin]
  );

  const isReview = activeStep === 6;

  return (
    <div className={cn("content-card card-auto", cardHover.soft, className)}>
      <div className="card-pad pb-0">
        <div className="flex flex-wrap items-start justify-between gap-g3">
          <div className="flex min-w-0 items-center gap-g2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FFA500]/10 orange-gradient-border text-[#FFA500]">
              <Box size={15} />
            </span>
            <div className="min-w-0">
              <h3 className="text-section-title">3D Digital Twin</h3>
              <p className="text-helper mt-g1">
                {twin.machineType || "No machine type selected"}
                {twin.machineName && (
                  <span className="text-muted-foreground"> · {twin.machineName}</span>
                )}
                {" — "}
                {STEP_CAPTION[activeStep] ?? STEP_CAPTION[1]}
              </p>
            </div>
          </div>
          <DigitalTwinControls activeView={view.view} onSelectView={selectView} />
        </div>
      </div>

      <div className="card-pad pt-g3">
        <div
          className={cn(
            "grid gap-g4",
            isReview ? "grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px]" : "grid-cols-1"
          )}
        >
          <div className="min-w-0">
            <React.Suspense
              fallback={
                <div
                  className={cn(
                    "w-full animate-pulse rounded-lg border border-border bg-surface",
                    isReview
                      ? "h-[300px] sm:h-[380px] xl:h-[440px]"
                      : "h-[240px] sm:h-[300px] xl:h-[340px]"
                  )}
                />
              }
            >
              <DigitalTwinViewer
                twin={twin}
                selectedKey={selectedKey}
                onSelect={setSelected}
                viewRequest={view}
                className={cn(
                  "w-full rounded-lg border border-border bg-brand-warm",
                  isReview
                    ? "h-[300px] sm:h-[380px] xl:h-[440px]"
                    : "h-[240px] sm:h-[300px] xl:h-[340px]"
                )}
                fallback={
                  <div className="flex h-full w-full flex-col items-center justify-center gap-g2 p-g4">
                    <div className="h-28 w-full max-w-[240px]">
                      <MachineIllustration type={twin.machineType} />
                    </div>
                    <p className="text-center text-xs text-muted-foreground">
                      3D view unavailable in this browser — showing the 2D schematic. Your
                      configuration is unaffected.
                    </p>
                  </div>
                }
              />
            </React.Suspense>

            <div className="mt-g2 flex flex-wrap items-center justify-between gap-g2">
              <Legend />
              <p className="text-xs text-muted-foreground">Drag to rotate · scroll to zoom</p>
            </div>

            {twin.model.schematic && (
              <p className="mt-g2 flex items-start gap-1.5 text-xs text-muted-foreground">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>
                  {twin.machineType
                    ? `No dedicated model for "${twin.machineType}" yet — showing a generic rotating machine with drive and non-drive ends.`
                    : "Showing a generic rotating machine until a Machine Type is selected in Step 1."}
                </span>
              </p>
            )}

            {activeSelection && (
              <TwinSelectionDetail
                className="mt-g3"
                bearing={selectedBearing}
                sensor={selectedSensor}
                equipmentId={equipmentId}
                onClose={() => setSelected(null)}
              />
            )}
          </div>

          {isReview && (
            <DigitalTwinSummary
              twin={twin}
              selectedKey={selectedKey}
              onSelect={selectByKey}
              className="min-w-0"
            />
          )}
        </div>
      </div>
    </div>
  );
}
