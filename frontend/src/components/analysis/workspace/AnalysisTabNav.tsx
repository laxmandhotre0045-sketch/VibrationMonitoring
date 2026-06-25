import React from "react";
import type { AnalysisTabId } from "@/types/analysis-tabs";
import { ANALYSIS_TABS } from "@/types/analysis-tabs";
import { cn } from "@/lib/utils";

interface AnalysisTabNavProps {
  activeTab: AnalysisTabId;
  onTabChange: (tab: AnalysisTabId) => void;
  className?: string;
}

export function AnalysisTabNav({ activeTab, onTabChange, className }: AnalysisTabNavProps) {
  return (
    <div
      className={cn(
        "analysis-tab-panel rounded-xl border border-border bg-[#FFFDF8] p-3 sm:p-3.5",
        "shadow-[0_2px_14px_rgba(21,54,109,0.07)]",
        className
      )}
      role="tablist"
      aria-label="Analysis views"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {ANALYSIS_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                "group relative flex min-h-[56px] w-full items-center justify-center gap-2.5",
                "rounded-[10px] border px-4 py-3.5 text-center",
                "text-sm font-semibold leading-snug",
                "cursor-pointer select-none",
                "transition-all duration-300 ease-out",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45 focus-visible:ring-offset-2",
                isActive
                  ? cn(
                      "orange-gradient-border-subtle -translate-y-0.5 border-transparent",
                      "bg-white text-signal-dark",
                      "shadow-[0_10px_28px_rgba(255,107,0,0.14)]",
                      "ring-1 ring-signal-light/30"
                    )
                  : cn(
                      "border-border bg-white text-brand/80",
                      "shadow-sm",
                      "hover:-translate-y-0.5 hover:border-signal-light/55 hover:bg-warm",
                      "hover:text-brand hover:shadow-[0_8px_20px_rgba(21,54,109,0.1)]"
                    )
              )}
            >
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors duration-300",
                  isActive
                    ? "bg-[#FFA500]/15 text-[#FFA500]"
                    : "bg-brand/[0.05] text-brand/55 group-hover:bg-[#FFA500]/10 group-hover:text-signal-dark"
                )}
              >
                <Icon size={20} strokeWidth={isActive ? 2.25 : 2} aria-hidden />
              </span>
              <span className="min-w-0 flex-1 text-left sm:text-center">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
