import type { LucideIcon } from "lucide-react";
import { BarChart3, HeartPulse, LineChart, TrendingUp } from "lucide-react";

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
