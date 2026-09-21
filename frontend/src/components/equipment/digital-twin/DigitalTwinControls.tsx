import React from "react";
import { Maximize2 } from "lucide-react";
import type { CameraViewId } from "./twin-scene";
import { cn } from "@/lib/utils";

interface DigitalTwinControlsProps {
  activeView: CameraViewId;
  onSelectView: (view: CameraViewId) => void;
  className?: string;
}

const VIEWS: { id: CameraViewId; label: string }[] = [
  { id: "front", label: "Front" },
  { id: "side", label: "Side" },
  { id: "top", label: "Top" },
];

/**
 * Explicit view buttons.
 *
 * The model can always be orbited by dragging, but a pointer gesture is not
 * discoverable and is awkward on a touch screen, so every view the operator
 * actually needs is also one tap away.
 */
export function DigitalTwinControls({
  activeView,
  onSelectView,
  className,
}: DigitalTwinControlsProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <button
        type="button"
        onClick={() => onSelectView("iso")}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold border transition-colors min-h-[32px]",
          activeView === "iso"
            ? "border-[#FF6B00] bg-[#FF6B00] text-white"
            : "border-border bg-white text-muted-foreground hover:text-foreground hover:border-[#FF6B00]/40"
        )}
      >
        <Maximize2 size={12} />
        Reset View
      </button>
      {VIEWS.map((view) => (
        <button
          key={view.id}
          type="button"
          onClick={() => onSelectView(view.id)}
          className={cn(
            "px-2.5 py-1.5 rounded-md text-xs font-semibold border transition-colors min-h-[32px]",
            activeView === view.id
              ? "border-[#FF6B00] bg-[#FF6B00]/10 text-[#FF6B00]"
              : "border-border bg-white text-muted-foreground hover:text-foreground hover:border-[#FF6B00]/40"
          )}
        >
          {view.label}
        </button>
      ))}
    </div>
  );
}
