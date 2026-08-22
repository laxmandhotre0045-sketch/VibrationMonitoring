import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { sensoVibeLogo, sensoVibeMark } from "@/images";
import { NAV_ITEMS } from "./nav-config";
import { useLayout } from "@/contexts/LayoutContext";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

const SIDEBAR_WIDTH = 320;
const SIDEBAR_COLLAPSED = 80;
const TAGLINE = "AI Powered Vibration Intelligence";

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  const { sidebarCollapsed, toggleSidebar } = useLayout();
  const { hasRole } = useAuth();
  const location = useLocation();

  const visibleNavItems = NAV_ITEMS.filter((item) => hasRole(item.roles));

  const isItemActive = (path: string, matchPaths?: string[]) => {
    if (matchPaths) return matchPaths.some((p) => location.pathname.startsWith(p));
    return location.pathname === path;
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="sidebar-shell"
    >
      <div
        className={cn(
          "logo-zone flex flex-col justify-between min-h-[90px] md:justify-center",
          sidebarCollapsed ? "px-g2 py-g4 items-center" : "px-g4 py-g4"
        )}
      >
        {/* Close button for mobile */}
        {onClose && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 md:hidden p-2 hover:bg-signal-light/10 rounded-lg transition-colors"
            aria-label="Close sidebar"
          >
            <X size={20} className="text-brand" />
          </button>
        )}
        <AnimatePresence mode="wait">
          {sidebarCollapsed ? (
            <motion.div
              key="collapsed"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center justify-center"
            >
              <img
                src={sensoVibeMark}
                alt="SensoVibe"
                className="w-[52px] h-[52px] object-contain"
              />
            </motion.div>
          ) : (
            <motion.div
              key="expanded"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="w-full"
            >
              <div className="inline-flex items-start max-w-[276px]">
                <img
                  src={sensoVibeLogo}
                  alt="SensoVibe"
                  className="block h-[60px] w-auto max-w-[252px] object-contain object-left"
                />
                <span className="mt-[13px] -ml-[3px] text-[8px] font-bold text-brand leading-none shrink-0">
                  TM
                </span>
              </div>
              <p className="mt-g1 text-sm font-medium text-brand/70 tracking-wide leading-snug">
                {TAGLINE}
              </p>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="sidebar-logo-divider" aria-hidden />
      </div>

      <nav className="flex-1 px-3 py-3 space-y-g1 overflow-y-auto scrollbar-thin">
        {!sidebarCollapsed && (
          <p className="px-3 mb-g2 text-overline text-[#FFA500]/85">
            Modules
          </p>
        )}
        {visibleNavItems.map((item) => {
          const routeActive = isItemActive(item.path, item.matchPaths);
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className="block group"
              onClick={() => onClose?.()}
            >
              <div
                className={cn(
                  "sidebar-nav-item",
                  routeActive && "sidebar-nav-item-active"
                )}
              >
                {routeActive && <span className="signal-nav-rail" aria-hidden />}
                <span
                  className={cn(
                    "flex items-center justify-center w-11 h-11 rounded-lg shrink-0 transition-colors duration-200",
                    routeActive
                      ? "bg-[#FFA500]/15 text-[#FFA500]"
                      : "bg-brand/[0.06] text-brand/55 group-hover:bg-[rgba(255,165,0,0.1)] group-hover:text-brand"
                  )}
                >
                  <Icon
                    size={26}
                    strokeWidth={routeActive ? 2.25 : 2}
                    aria-hidden
                  />
                </span>
                {!sidebarCollapsed && (
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        "text-base truncate leading-tight",
                        routeActive ? "font-semibold text-[#FFA500]" : "font-semibold text-brand/85"
                      )}
                    >
                      {item.label}
                    </p>
                  </div>
                )}
              </div>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 py-3 orange-gradient-border-top shrink-0">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center gap-2 px-3 min-h-[44px] rounded-lg text-brand/75 hover:text-[#FFA500] hover:bg-[rgba(255,165,0,0.08)] transition-all duration-200 text-sm font-semibold"
        >
          {sidebarCollapsed ? <ChevronRight size={22} /> : <><ChevronLeft size={22} /> Collapse</>}
        </button>
      </div>
    </motion.aside>
  );
}
