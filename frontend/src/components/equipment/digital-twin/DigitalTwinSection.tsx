import React from "react";
import { isFeatureEnabled } from "@/lib/feature-flags";
import { DigitalTwinPanel } from "./DigitalTwinPanel";
import { DigitalTwinPanelV2 } from "./DigitalTwinPanelV2";

interface DigitalTwinSectionProps {
  activeStep: number;
  equipmentId?: string;
  className?: string;
}

/**
 * Picks the Digital Twin implementation.
 *
 * `digitalTwinV2` selects the rebuilt viewer — GLB models, studio lighting,
 * x-ray and HTML labels. With the flag off the original viewer renders
 * unchanged, which is the escape hatch while v2 is being signed off.
 *
 * Both sides lazy-load their own three.js chunk, so whichever one is switched
 * off costs nothing but this import.
 *
 * Once v2 is the only implementation, delete `DigitalTwinPanel`,
 * `DigitalTwinViewer`, `twin-scene.ts`, `DigitalTwinControls`,
 * `DigitalTwinSummary` and this file, and point `EquipmentForm` straight at
 * `DigitalTwinPanelV2`.
 */
export function DigitalTwinSection(props: DigitalTwinSectionProps) {
  return isFeatureEnabled("digitalTwinV2") ? (
    <DigitalTwinPanelV2 {...props} />
  ) : (
    <DigitalTwinPanel {...props} />
  );
}
