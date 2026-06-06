import React from "react";
import { cn } from "@/lib/utils";

interface VibrationWaveProps {
  className?: string;
}

/** Subtle brand wave — signal accent only, never a surface fill */
export function VibrationWave({ className }: VibrationWaveProps) {
  return (
    <svg
      viewBox="0 0 240 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-auto", className)}
      aria-hidden
    >
      <path
        d="M0 12 C20 4, 40 20, 60 12 S100 4, 120 12 S160 20, 180 12 S220 4, 240 12"
        stroke="#F5A623"
        strokeOpacity={0.35}
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M0 16 C20 10, 40 22, 60 16 S100 10, 120 16 S160 22, 180 16 S220 10, 240 16"
        stroke="#D98C00"
        strokeOpacity={0.2}
        strokeWidth="1"
        strokeLinecap="round"
      />
    </svg>
  );
}
