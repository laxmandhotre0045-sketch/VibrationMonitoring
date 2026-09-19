import {
  LayoutDashboard,
  Cpu,
  Activity,
  Database,
  Sparkles,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  matchPaths?: string[];
  roles: string[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    active: false,
    roles: ["super_admin", "admin", "user"],
  },
  {
    path: "/equipment",
    label: "Equipment Master",
    icon: Cpu,
    active: true,
    matchPaths: ["/equipment"],
    roles: ["super_admin", "admin", "user"],
  },
  {
    path: "/analysis",
    label: "Vibration Analysis",
    icon: Activity,
    active: true,
    matchPaths: ["/analysis"],
    roles: ["super_admin", "admin", "user"],
  },
  {
    path: "/sensor-data",
    label: "Sensor Data",
    icon: Database,
    active: true,
    matchPaths: ["/sensor-data"],
    roles: ["super_admin", "admin", "user"],
  },
  {
    path: "/ai-analysis",
    label: "AI Analysis",
    icon: Sparkles,
    active: true,
    matchPaths: ["/ai-analysis"],
    roles: ["super_admin", "admin", "user"],
  },
  {
    path: "/settings",
    label: "Settings",
    icon: Settings,
    active: true,
    matchPaths: ["/settings"],
    roles: ["super_admin", "admin"],
  },
];

/**
 * Sentinel for "no plant filter". Real plant names come from
 * GET /api/v1/lookups/plants (distinct plant_name in the equipment master).
 */
export const ALL_PLANTS = "All Plants";
