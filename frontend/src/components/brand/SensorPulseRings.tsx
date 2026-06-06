import React from "react";
import { cn } from "@/lib/utils";

interface SensorPulseRingsProps {
  className?: string;
}

/**
 * Subtle concentric sensor pulses — extremely slow cycle (18s).
 * Placed behind machine visualization only.
 */
export function SensorPulseRings({ className }: SensorPulseRingsProps) {
  const rings = [
    { size: 72, delay: "0s" },
    { size: 108, delay: "6s" },
    { size: 144, delay: "12s" },
  ];

  return (
    <div
      className={cn(
        "absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden",
        className
      )}
      aria-hidden
    >
      {rings.map((ring) => (
        <div
          key={ring.size}
          className="absolute rounded-full border border-[#F5A623] sensor-pulse-ring-slow"
          style={{
            width: ring.size,
            height: ring.size,
            animationDelay: ring.delay,
          }}
        />
      ))}
      <div className="absolute w-2 h-2 rounded-full bg-[#D98C00] opacity-[0.12]" />
    </div>
  );
}
