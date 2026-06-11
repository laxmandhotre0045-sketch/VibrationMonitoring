import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "@/components/ui/Toast";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LayoutProvider } from "@/contexts/LayoutContext";
import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/pages/Dashboard";
import { EquipmentMasterList } from "@/pages/EquipmentMasterList";
import { NewEquipmentPage, EditEquipmentPage } from "@/pages/EquipmentMaster";
import { SettingsPage } from "@/pages/ModulePages";
import { VibrationAnalysisPage } from "@/pages/VibrationAnalysis";

export default function App() {
  return (
    <ThemeProvider>
      <LayoutProvider>
        <ToastProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/equipment" element={<EquipmentMasterList />} />
              <Route path="/equipment/new" element={<NewEquipmentPage />} />
              <Route path="/equipment/:id/edit" element={<EditEquipmentPage />} />
              <Route path="/analysis" element={<VibrationAnalysisPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </ToastProvider>
      </LayoutProvider>
    </ThemeProvider>
  );
}
