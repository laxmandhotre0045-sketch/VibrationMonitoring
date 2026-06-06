import {
  LayoutDashboard,
  Cpu,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  matchPaths?: string[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    active: false,
  },
  {
    path: "/equipment",
    label: "Equipment Master",
    icon: Cpu,
    active: true,
    matchPaths: ["/equipment"],
  },
  {
    path: "/settings",
    label: "Settings",
    icon: Settings,
    active: false,
  },
];

export const PLANTS = [
  "All Plants",
  "Plant A — Mumbai",
  "Plant B — Pune",
  "Plant C — Chennai",
  "Plant D — Ahmedabad",
];
