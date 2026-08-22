import {
  LayoutDashboard,
  Cpu,
  Activity,
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
