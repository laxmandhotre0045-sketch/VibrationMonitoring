import { cn } from "@/lib/utils";

/**
 * Spacing for the Vibration Analysis workspace.
 *
 * Aliases onto the shared ladder in `@/lib/layout` rather than carrying its own
 * numbers. Kept as named exports because the analysis tree imports them in ~20
 * places; the values behind them are no longer independent.
 */
export const analysisPageStack = "page-stack";
export const analysisCardPad = "card-pad";
export const analysisBodyStack = "space-y-g3";
export const analysisGridGap = "gap-g3";

export const analysisSelectClass = cn(
  "w-full px-g2 py-1.5 text-sm font-normal rounded-md transition-colors appearance-none cursor-pointer",
  "bg-white text-foreground border border-border",
  "focus:outline-none focus:border-signal-light focus:ring-1 focus:ring-[rgba(245,166,35,0.22)]",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);

export const analysisInputClass = "py-1.5 px-g2 text-sm h-9";

export const analysisKpiClass =
  "rounded-md border border-border bg-white px-g2 py-g2 min-w-[112px]";

export const analysisKpiLabelClass =
  "text-xs font-semibold uppercase tracking-wide text-muted-foreground leading-none";

export const analysisKpiValueClass = "mt-g1 text-base font-bold text-foreground leading-tight";

export const analysisSectionIconBoxClass =
  "w-10 h-10 rounded-lg bg-[#FFA500]/10 orange-gradient-border flex items-center justify-center text-[#FFA500] shrink-0";

export const analysisSectionIconSize = 20;

export const analysisChannelBtnClass = cn(
  "rounded-md px-2.5 py-1.5 text-sm font-semibold transition-colors",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]"
);
