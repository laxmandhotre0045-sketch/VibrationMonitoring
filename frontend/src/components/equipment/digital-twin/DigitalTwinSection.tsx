import React from "react";
import { isFeatureEnabled } from "@/lib/feature-flags";
import { DigitalTwinPanel } from "./DigitalTwinPanel";
import { DigitalTwinPanelV2 } from "./DigitalTwinPanelV2";
import { SenviaLibraryPanel } from "./SenviaLibraryPanel";

interface DigitalTwinSectionProps {
  activeStep: number;
  equipmentId?: string;
  className?: string;
}

/**
 * Picks the 3D implementation.
 *
 * `senvia3dLibrary` is the shipped one: the Senvia 3D equipment library from
 * the kit, embedded whole — 48 machines, correct rotation, the full toolbar. It
 * replaced the hand-built viewers rather than extending them, because those
 * re-derived a handful of machines that the kit already draws properly.
 *
 * The two older viewers stay behind it as escape hatches. `digitalTwinV2` is
 * the GLB viewer with studio lighting and HTML labels; with both flags off the
 * original renders unchanged. Each lazy-loads its own three.js chunk, so the
 * ones not in use cost nothing but these imports.
 *
 * Once the library has been signed off on a customer site, delete
 * `DigitalTwinPanel`, `DigitalTwinPanelV2`, `DigitalTwinViewer`,
 * `DigitalTwinViewerV2`, `twin-scene.ts`, `DigitalTwinControls`,
 * `DigitalTwinSummary` and this file, and point `EquipmentForm` straight at
 * `SenviaLibraryPanel`.
 */
export function DigitalTwinSection(props: DigitalTwinSectionProps) {
  if (isFeatureEnabled("senvia3dLibrary")) return <SenviaLibraryPanel {...props} />;
  return isFeatureEnabled("digitalTwinV2") ? (
    <DigitalTwinPanelV2 {...props} />
  ) : (
    <DigitalTwinPanel {...props} />
  );
}
