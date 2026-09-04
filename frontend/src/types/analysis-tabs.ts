import type { LucideIcon } from "lucide-react";
import { BarChart3, HeartPulse, LineChart, TrendingUp } from "lucide-react";

/**
 * Top-level analysis views.
 *
 * Waterfall, cascade, vector, orbit, migration and raw data were tabs of their
 * own until they moved under Detailed Analysis → Advanced Plots & Diagnostics.
 * They are selected there now, so listing them here too would mount each chart
 * in two places.
 */
export type AnalysisTabId = "health" | "trend" | "detailed" | "statistics";

export const ANALYSIS_TABS: {
  id: AnalysisTabId;
  label: string;
  icon: LucideIcon;
}[] = [
  { id: "health", label: "Status (Health)", icon: HeartPulse },
  { id: "trend", label: "Trend", icon: TrendingUp },
  { id: "detailed", label: "Detailed Analysis", icon: LineChart },
  { id: "statistics", label: "Statistics", icon: BarChart3 },
];
