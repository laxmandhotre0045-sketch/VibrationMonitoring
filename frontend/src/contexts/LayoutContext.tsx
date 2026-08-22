import React, { createContext, useContext, useState } from "react";
import { ALL_PLANTS } from "@/components/layout/nav-config";

interface LayoutContextValue {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  selectedPlant: string;
  setSelectedPlant: (plant: string) => void;
}

const LayoutContext = createContext<LayoutContextValue>({
  sidebarCollapsed: false,
  toggleSidebar: () => {},
  selectedPlant: ALL_PLANTS,
  setSelectedPlant: () => {},
});

export function LayoutProvider({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedPlant, setSelectedPlant] = useState(ALL_PLANTS);

  const toggleSidebar = () => setSidebarCollapsed((c) => !c);

  return (
    <LayoutContext.Provider
      value={{ sidebarCollapsed, toggleSidebar, selectedPlant, setSelectedPlant }}
    >
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayout() {
  return useContext(LayoutContext);
}
