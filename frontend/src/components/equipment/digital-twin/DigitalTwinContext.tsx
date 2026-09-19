import React, { createContext, useContext, useMemo, useState } from "react";
import type { MountingRowInput } from "@/lib/digital-twin/twin-config";

/**
 * The six standard rows of Step 5's "Sensor Mounting & Orientation" table.
 *
 * These rows have always been local UI state — they are *not* sensor records
 * and are not saved with the equipment. That is unchanged here: the state has
 * only been lifted out of `SensorsOrientationTab` so the Digital Twin viewer,
 * which renders outside that tab, can read the same values the table shows.
 *
 * Additional Sensors are untouched by this: they stay in the react-hook-form
 * `sensors` field array and continue to persist exactly as before.
 */
export interface MountingRow {
  /** Fixed row name — "DE Horizontal", "NDE Axial" … */
  label: string;
  selectedMounting: string;
  selectedOrientation: string;
}

export const DEFAULT_MOUNTING_ROWS: MountingRow[] = [
  { label: "DE Horizontal", selectedMounting: "Bearing Housing DE", selectedOrientation: "Horizontal" },
  { label: "DE Vertical", selectedMounting: "Bearing Housing DE", selectedOrientation: "Vertical" },
  { label: "DE Axial", selectedMounting: "Bearing Housing DE", selectedOrientation: "Axial" },
  { label: "NDE Horizontal", selectedMounting: "Bearing Housing NDE", selectedOrientation: "Horizontal" },
  { label: "NDE Vertical", selectedMounting: "Bearing Housing NDE", selectedOrientation: "Vertical" },
  { label: "NDE Axial", selectedMounting: "Bearing Housing NDE", selectedOrientation: "Axial" },
];

interface MountingRowsValue {
  rows: MountingRow[];
  setRows: React.Dispatch<React.SetStateAction<MountingRow[]>>;
}

const MountingRowsContext = createContext<MountingRowsValue | null>(null);

export function MountingRowsProvider({ children }: { children: React.ReactNode }) {
  const [rows, setRows] = useState<MountingRow[]>(DEFAULT_MOUNTING_ROWS);
  const value = useMemo(() => ({ rows, setRows }), [rows]);
  return <MountingRowsContext.Provider value={value}>{children}</MountingRowsContext.Provider>;
}

/**
 * The mounting rows.
 *
 * Falls back to its own state when no provider is present, so the sensors tab
 * keeps working standalone rather than throwing.
 */
export function useMountingRows(): MountingRowsValue {
  const context = useContext(MountingRowsContext);
  const [fallbackRows, setFallbackRows] = useState<MountingRow[]>(DEFAULT_MOUNTING_ROWS);
  const fallback = useMemo(
    () => ({ rows: fallbackRows, setRows: setFallbackRows }),
    [fallbackRows]
  );
  return context ?? fallback;
}

/** The rows in the shape `resolveTwin` expects. */
export function toMountingRowInputs(rows: MountingRow[]): MountingRowInput[] {
  return rows.map((row) => ({
    label: row.label,
    mountingLocation: row.selectedMounting,
    orientation: row.selectedOrientation,
  }));
}
