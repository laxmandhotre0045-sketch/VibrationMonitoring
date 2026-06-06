import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "@/components/ui/Toast";
import { Dashboard } from "@/pages/Dashboard";
import { NewEquipmentPage, EditEquipmentPage } from "@/pages/EquipmentMaster";

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/equipment/new" element={<NewEquipmentPage />} />
        <Route path="/equipment/:id/edit" element={<EditEquipmentPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ToastProvider>
  );
}
