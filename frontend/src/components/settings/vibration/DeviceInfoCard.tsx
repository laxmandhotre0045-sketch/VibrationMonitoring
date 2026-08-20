import React from "react";
import { Cpu, Radio } from "lucide-react";
import type { VibrationDeviceInfo } from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

interface DeviceInfoCardProps {
  device: VibrationDeviceInfo;
  className?: string;
}

export function DeviceInfoCard({ device, className }: DeviceInfoCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-g3 rounded-lg border border-border bg-white px-g4 py-g3 sm:flex-row sm:items-center sm:justify-between",
        "shadow-sm border-l-2 border-l-signal-light",
        className
      )}
    >
      <div className="flex items-start gap-3 min-w-0">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/[0.06] text-brand">
          <Cpu size={20} aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-overline text-muted-foreground">Device</p>
          <p className="text-sm font-semibold text-foreground truncate">{device.deviceLabel}</p>
          <p className="text-xs text-muted-foreground mt-g1 font-mono">{device.deviceId}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 sm:pl-4 sm:border-l sm:border-border">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FFA500]/10 text-signal-dark">
          <Radio size={18} aria-hidden />
        </span>
        <div>
          <p className="text-overline text-muted-foreground">Mode</p>
          <p className="text-sm font-bold text-brand">{device.mode}</p>
        </div>
      </div>
    </div>
  );
}
