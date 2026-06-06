import React, { createContext, useContext, useState } from "react";

interface LayoutContextValue {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  selectedPlant: string;
  setSelectedPlant: (plant: string) => void;
}

const LayoutContext = createContext<LayoutContextValue>({
  sidebarCollapsed: false,
  toggleSidebar: () => {},
  selectedPlant: "All Plants",
  setSelectedPlant: () => {},
});

export function LayoutProvider({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedPlant, setSelectedPlant] = useState("All Plants");

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
