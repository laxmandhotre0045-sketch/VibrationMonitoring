import { cn } from "@/lib/utils";

/** Shared spacing tokens for the Vibration Analysis dashboard. */
export const analysisPageStack = "space-y-4";
export const analysisCardPad = "p-4";
export const analysisBodyStack = "space-y-3";
export const analysisGridGap = "gap-3";

export const analysisSelectClass = cn(
  "w-full px-3 py-2 text-base font-normal rounded-md transition-colors appearance-none cursor-pointer",
  "bg-white text-foreground border border-border",
  "focus:outline-none focus:border-signal-light focus:ring-1 focus:ring-[rgba(245,166,35,0.22)]",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);

export const analysisInputClass = "py-2 px-3 text-base h-10";

export const analysisKpiClass =
  "rounded-md border border-border bg-white px-2.5 py-2 min-w-[120px]";

export const analysisKpiLabelClass =
  "text-xs font-semibold uppercase tracking-wide text-muted-foreground leading-none";

export const analysisKpiValueClass = "mt-1 text-base font-bold text-foreground leading-tight";

export const analysisSectionIconBoxClass =
  "w-12 h-12 rounded-lg bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0";

export const analysisSectionIconSize = 26;

export const analysisChannelBtnClass = cn(
  "rounded-md px-2.5 py-1.5 text-sm font-semibold transition-colors",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]"
);
