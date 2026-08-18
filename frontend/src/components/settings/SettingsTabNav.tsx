import React from "react";
import { Activity, Users, type LucideIcon } from "lucide-react";
import type { SettingsModuleId } from "@/types/vibration-settings";
import { cn } from "@/lib/utils";

interface SettingsTab {
  id: SettingsModuleId;
  label: string;
  description: string;
  icon: LucideIcon;
  available: boolean;
}

const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "vibration",
    label: "Vibration Settings",
    description: "Channels, mapping & thresholds",
    icon: Activity,
    available: true,
  },
  {
    id: "platform",
    label: "Platform",
    description: "Users, plants & integrations",
    icon: Users,
    available: true,
  },
];

interface SettingsTabNavProps {
  activeModule: SettingsModuleId;
  onModuleChange: (module: SettingsModuleId) => void;
  className?: string;
}

export function SettingsTabNav({ activeModule, onModuleChange, className }: SettingsTabNavProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-[#FFFDF8] p-3 shadow-[0_2px_14px_rgba(21,54,109,0.07)]",
        className
      )}
      role="tablist"
      aria-label="Settings modules"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SETTINGS_TABS.map((tab) => {
          const isActive = activeModule === tab.id;
          const Icon = tab.icon;
          const disabled = !tab.available;

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              disabled={disabled}
              onClick={() => !disabled && onModuleChange(tab.id)}
              className={cn(
                "group relative flex min-h-[56px] w-full items-center gap-2.5 rounded-[10px] border px-4 py-3.5 text-left",
                "text-sm font-semibold transition-all duration-300",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45 focus-visible:ring-offset-2",
                disabled && "cursor-not-allowed opacity-55",
                isActive
                  ? "orange-gradient-border-subtle border-transparent bg-white text-signal-dark shadow-[0_10px_28px_rgba(255,107,0,0.14)] ring-1 ring-signal-light/30"
                  : "border-border bg-white text-brand/80 shadow-sm hover:border-signal-light/55 hover:bg-warm hover:text-brand"
              )}
            >
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                  isActive
                    ? "bg-[#FFA500]/15 text-[#FFA500]"
                    : "bg-brand/[0.05] text-brand/55 group-hover:bg-[#FFA500]/10 group-hover:text-signal-dark"
                )}
              >
                <Icon size={20} strokeWidth={isActive ? 2.25 : 2} aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block">{tab.label}</span>
                <span className="block text-xs font-medium text-muted-foreground mt-0.5">
                  {tab.description}
                  {!tab.available && " · Coming soon"}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
