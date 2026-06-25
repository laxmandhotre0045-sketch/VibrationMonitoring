import React from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface HealthInfoBannerProps {
  message: string;
  hasThresholds?: boolean;
  className?: string;
}

export function HealthInfoBanner({ message, hasThresholds = false, className }: HealthInfoBannerProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-md border px-3 py-2.5",
        hasThresholds
          ? "border-machine-healthy/30 bg-machine-healthy/5 border-l-2 border-l-machine-healthy"
          : "border-border bg-surface/60 border-l-2 border-l-signal-light",
        className
      )}
      role="status"
    >
      <Info
        size={22}
        className={cn(
          "shrink-0 mt-0.5",
          hasThresholds ? "text-machine-healthy" : "text-signal-dark"
        )}
        aria-hidden
      />
      <p className="text-sm text-foreground leading-snug">{message}</p>
    </div>
  );
}
