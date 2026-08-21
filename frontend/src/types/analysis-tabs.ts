import type { LucideIcon } from "lucide-react";
import { BarChart3, Box, CircleDot, Compass, HeartPulse, LineChart, TrendingUp } from "lucide-react";

export type AnalysisTabId =
  | "health"
  | "trend"
  | "detailed"
  | "waterfall"
  | "vector"
  | "orbit"
  | "statistics";

export const ANALYSIS_TABS: {
  id: AnalysisTabId;
  label: string;
  icon: LucideIcon;
}[] = [
  { id: "health", label: "Status (Health)", icon: HeartPulse },
  { id: "trend", label: "Trend", icon: TrendingUp },
  { id: "detailed", label: "Detailed Analysis", icon: LineChart },
  { id: "waterfall", label: "Waterfall & Cascade", icon: Box },
  { id: "vector", label: "Vibration Vector", icon: Compass },
  { id: "orbit", label: "Casing Orbit", icon: CircleDot },
  { id: "statistics", label: "Statistics", icon: BarChart3 },
];
