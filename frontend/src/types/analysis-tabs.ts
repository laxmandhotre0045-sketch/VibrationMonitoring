import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Box,
  CircleDot,
  Compass,
  HeartPulse,
  LineChart,
  Move3D,
  Radio,
  TrendingUp,
} from "lucide-react";

export type AnalysisTabId =
  | "health"
  | "trend"
  | "detailed"
  | "waterfall"
  | "vector"
  | "orbit"
  | "migration"
  | "raw"
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
  { id: "migration", label: "1× Amplitude Migration", icon: Move3D },
  { id: "raw", label: "Raw Data", icon: Radio },
  { id: "statistics", label: "Statistics", icon: BarChart3 },
];
