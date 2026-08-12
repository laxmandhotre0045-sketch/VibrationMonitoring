import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Bell, ChevronDown, Building2, Menu, X } from "lucide-react";
import { useLayout } from "@/contexts/LayoutContext";
import { PLANTS } from "./nav-config";
import { cn } from "@/lib/utils";

const navBtn = "bg-white border border-border hover:border-signal-light transition-colors rounded-lg";

interface TopNavProps {
  onMenuClick?: () => void;
  menuOpen?: boolean;
}

export function TopNav({ onMenuClick, menuOpen }: TopNavProps) {
  const { selectedPlant, setSelectedPlant } = useLayout();
  const [searchFocused, setSearchFocused] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [notifications] = useState(3);

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-2 sm:gap-4 px-4 sm:px-6 py-2 sm:py-3 bg-warm border-b border-border shadow-nav">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="md:hidden p-2 hover:bg-signal-light/10 rounded-lg transition-colors"
        aria-label="Toggle menu"
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Search bar - responsive */}
      <div className={cn(
        "relative hidden sm:block transition-all duration-200 flex-1 sm:flex-initial",
        searchFocused ? "w-full sm:w-[400px]" : "w-full sm:w-80"
      )}>
        <Search size={16} className={cn("absolute left-3 top-1/2 -translate-y-1/2", searchFocused ? "text-signal-light" : "text-muted-foreground")} />
        <input
          type="text"
          placeholder="Search equipment, plants, alerts..."
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          className="w-full pl-10 pr-4 py-2 text-sm rounded-lg bg-white border border-border text-brand placeholder:text-muted-foreground focus:outline-none focus:border-signal-light focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]"
        />
      </div>

      {/* Mobile search icon */}
      <button className="sm:hidden p-2 hover:bg-signal-light/10 rounded-lg transition-colors">
        <Search size={18} className="text-brand" />
      </button>

      <div className="flex items-center gap-1 sm:gap-2 ml-auto">
        <div className="relative">
          <button
            onClick={() => setPlantOpen(!plantOpen)}
            className={cn("flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-2 text-xs sm:text-sm font-medium text-brand", navBtn)}
            title={selectedPlant}
          >
            <Building2 size={15} className="text-signal-dark flex-shrink-0" />
            <span className="hidden md:inline max-w-[100px] lg:max-w-[140px] truncate">{selectedPlant}</span>
            <ChevronDown size={14} className="text-muted-foreground hidden sm:block" />
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
                  className="absolute right-0 top-full mt-1 w-56 z-20 py-1 rounded-lg bg-white border border-border shadow-card-hover"
                >
                  {PLANTS.map((plant) => (
                    <button
                      key={plant}
                      onClick={() => { setSelectedPlant(plant); setPlantOpen(false); }}
                      className={cn(
                        "w-full text-left px-4 py-2 text-sm transition-colors",
                        selectedPlant === plant ? "text-brand bg-white font-medium border-l-2 border-l-signal-dark" : "text-brand/80 hover:bg-warm"
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

        <button className={cn("relative p-2", navBtn)}>
          <Bell size={18} className="text-brand" />
          {notifications > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center text-[9px] font-bold text-white bg-signal-dark rounded-full">
              {notifications}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
