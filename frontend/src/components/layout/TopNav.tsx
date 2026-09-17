import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Search, ChevronDown, Building2, LogOut, User, Menu, X } from "lucide-react";
import { useLayout } from "@/contexts/LayoutContext";
import { useAuth } from "@/contexts/AuthContext";
import { getLookup } from "@/api/equipment";
import { NotificationBell } from "./NotificationBell";
import { ALL_PLANTS } from "./nav-config";
import { primaryRole, roleLabel } from "@/lib/role-access";
import { cn } from "@/lib/utils";

const navBtn = "bg-white border border-border hover:border-signal-light transition-colors rounded-lg";

interface TopNavProps {
  onMenuClick?: () => void;
  menuOpen?: boolean;
}

export function TopNav({ onMenuClick, menuOpen }: TopNavProps) {
  const { selectedPlant, setSelectedPlant } = useLayout();
  const { user, roles, logout } = useAuth();
  const [searchFocused, setSearchFocused] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const badge = roleLabel(primaryRole(roles));

  const { data: plants } = useQuery({
    queryKey: ["lookup", "plants"],
    queryFn: () => getLookup("plants"),
    staleTime: 5 * 60_000,
  });
  const plantOptions = [ALL_PLANTS, ...(plants ?? [])];

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-g3 px-g4 py-g3 bg-warm border-b border-border shadow-nav">
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          className={cn("md:hidden flex items-center justify-center p-2 shrink-0", navBtn)}
        >
          {menuOpen ? <X size={20} className="text-brand" /> : <Menu size={20} className="text-brand" />}
        </button>
      )}
      <div className={cn("relative hidden md:block transition-all duration-200", searchFocused ? "w-[400px]" : "w-80")}>
        <Search size={16} className={cn("absolute left-3 top-1/2 -translate-y-1/2", searchFocused ? "text-signal-light" : "text-muted-foreground")} />
        <input
          type="text"
          placeholder="Search equipment, plants, alerts…"
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          className="w-full pl-10 pr-4 py-2.5 text-base font-normal rounded-lg bg-white border border-border text-brand placeholder:text-placeholder placeholder:font-normal focus:outline-none focus:border-signal-light focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]"
        />
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <div className="relative">
          <button onClick={() => setPlantOpen(!plantOpen)} className={cn("flex items-center gap-2 px-3 py-2 text-base font-semibold text-brand", navBtn)}>
            <Building2 size={15} className="text-signal-dark" />
            <span className="hidden sm:inline max-w-[140px] truncate">{selectedPlant}</span>
            <ChevronDown size={14} className="text-muted-foreground" />
          </button>
          <AnimatePresence>
            {plantOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setPlantOpen(false)} />
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-g1 w-56 z-20 py-1 rounded-lg bg-white border border-border shadow-card-hover"
                >
                  {plantOptions.map((plant) => (
                    <button
                      key={plant}
                      onClick={() => { setSelectedPlant(plant); setPlantOpen(false); }}
                      className={cn(
                        "w-full text-left px-4 py-2.5 text-base transition-colors",
                        selectedPlant === plant ? "text-brand bg-white font-semibold border-l-2 border-l-signal-dark" : "text-brand/90 font-medium hover:bg-warm"
                      )}
                    >
                      {plant}
                    </button>
                  ))}
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>

        <NotificationBell className={navBtn} />

        <div className="relative">
          <button
            onClick={() => setUserOpen(!userOpen)}
            className={cn("flex items-center gap-2.5 px-3 py-2 text-base font-semibold text-brand", navBtn)}
          >
            <div className="w-7 h-7 rounded-full bg-brand/8 border border-border flex items-center justify-center shrink-0">
              <User size={14} className="text-brand" />
            </div>
            <div className="hidden sm:flex flex-col items-start leading-tight">
              <span className="text-sm font-semibold text-brand max-w-[120px] truncate">
                {user?.full_name ?? "User"}
              </span>
              <span className="text-[10px] font-bold tracking-wide text-signal-dark uppercase">
                {badge}
              </span>
            </div>
            <ChevronDown size={14} className="text-muted-foreground hidden sm:block" />
          </button>
          <AnimatePresence>
            {userOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setUserOpen(false)} />
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-g1 w-64 z-20 py-2 rounded-lg bg-white border border-border shadow-card-hover"
                >
                  <div className="px-4 py-2.5 border-b border-border">
                    <p className="text-sm font-semibold text-brand truncate">{user?.full_name}</p>
                    <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
                    <span className="inline-block mt-g2 text-xs font-bold tracking-wide px-2 py-0.5 rounded-md bg-white text-brand border border-signal-light/50 uppercase">
                      {badge}
                    </span>
                  </div>
                  <button
                    onClick={() => { setUserOpen(false); logout(); }}
                    className="w-full flex items-center gap-2.5 px-4 py-2.5 text-base font-medium text-brand/90 hover:bg-warm hover:text-destructive transition-colors"
                  >
                    <LogOut size={16} />
                    Sign Out
                  </button>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
