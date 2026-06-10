import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Bell, ChevronDown, Building2 } from "lucide-react";
import { useLayout } from "@/contexts/LayoutContext";
import { PLANTS } from "./nav-config";
import { cn } from "@/lib/utils";

const navBtn = "bg-white border border-border hover:border-signal-light transition-colors rounded-lg";

export function TopNav() {
  const { selectedPlant, setSelectedPlant } = useLayout();
  const [searchFocused, setSearchFocused] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [notifications] = useState(3);

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-4 px-6 py-3 bg-warm border-b border-border shadow-nav">
      <div className={cn("relative hidden md:block transition-all duration-200", searchFocused ? "w-[400px]" : "w-80")}>
        <Search size={16} className={cn("absolute left-3 top-1/2 -translate-y-1/2", searchFocused ? "text-signal-light" : "text-muted-foreground")} />
        <input
          type="text"
          placeholder="Search equipment, plants, alerts..."
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
                  className="absolute right-0 top-full mt-1 w-56 z-20 py-1 rounded-lg bg-white border border-border shadow-card-hover"
                >
                  {PLANTS.map((plant) => (
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

        <button className={cn("relative p-2", navBtn)}>
          <Bell size={18} className="text-brand" />
          {notifications > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center text-[10px] font-bold text-white bg-signal-dark rounded-full">
              {notifications}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
