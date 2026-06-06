import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { sensoVibeLogo, sensoVibeMark } from "@/images";
import { NAV_ITEMS } from "./nav-config";
import { useLayout } from "@/contexts/LayoutContext";
import { cn } from "@/lib/utils";

const SIDEBAR_WIDTH = 320;
const SIDEBAR_COLLAPSED = 80;
const TAGLINE = "AI Powered Vibration Intelligence";

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useLayout();
  const location = useLocation();

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
          "logo-zone flex flex-col justify-center min-h-[90px]",
          sidebarCollapsed ? "px-3 py-5 items-center" : "px-6 py-5"
        )}
      >
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
                <span className="mt-[13px] -ml-[3px] text-[7px] font-bold text-brand leading-none shrink-0">
                  TM
                </span>
              </div>
              <p className="mt-1.5 text-[11px] font-medium text-brand/50 tracking-wide leading-snug">
                {TAGLINE}
              </p>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="sidebar-logo-divider" aria-hidden />
      </div>

      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto scrollbar-thin">
        {!sidebarCollapsed && (
          <p className="px-3 mb-2 text-[11px] font-semibold text-[#FFA500]/70 uppercase tracking-widest">
            Modules
          </p>
        )}
        {NAV_ITEMS.map((item) => {
          const routeActive = isItemActive(item.path, item.matchPaths);
          const Icon = item.icon;

          return (
            <NavLink key={item.path} to={item.path} className="block group">
              <div
                className={cn(
                  "sidebar-nav-item",
                  routeActive && "sidebar-nav-item-active"
                )}
              >
                {routeActive && <span className="signal-nav-rail" aria-hidden />}
                <Icon
                  size={21}
                  strokeWidth={routeActive ? 2.25 : 2}
                  className={cn(
                    "shrink-0 transition-colors duration-200",
                    routeActive ? "text-[#FFA500]" : "text-brand/55 group-hover:text-brand"
                  )}
                />
                {!sidebarCollapsed && (
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        "text-base truncate leading-tight",
                        routeActive ? "font-semibold text-[#FFA500]" : "font-medium"
                      )}
                    >
                      {item.label}
                    </p>
                    {!item.active && (
                      <p className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5">
                        <Clock size={10} /> Coming Soon
                      </p>
                    )}
                  </div>
                )}
              </div>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 py-3 border-t border-[#FFA500]/20 shrink-0">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center gap-2 px-3 min-h-[44px] rounded-lg text-brand/60 hover:text-[#FFA500] hover:bg-[rgba(255,165,0,0.08)] transition-all duration-200 text-sm font-medium"
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <><ChevronLeft size={18} /> Collapse</>}
        </button>
      </div>
    </motion.aside>
  );
}
