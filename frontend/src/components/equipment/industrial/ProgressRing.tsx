import React from "react";
import { cn } from "@/lib/utils";

interface ProgressRingProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  trackColor?: string;
  label: string;
  sublabel?: string;
  className?: string;
}

export function ProgressRing({
  value,
  size = 60,
  strokeWidth = 5,
  color = "#D98C00",
  trackColor = "#E5E7EB",
  label,
  sublabel,
  className,
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <div className={cn("flex items-center gap-g3", className)}>
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={trackColor} strokeWidth={strokeWidth} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-base font-bold text-signal-dark">
          {value}%
        </span>
      </div>
      <div className="min-w-0">
        <p className="text-lg font-semibold text-brand leading-tight">{label}</p>
        {sublabel && <p className="text-helper mt-0.5">{sublabel}</p>}
      </div>
    </div>
  );
}
