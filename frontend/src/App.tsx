import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "@/components/ui/Toast";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LayoutProvider } from "@/contexts/LayoutContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { Dashboard } from "@/pages/Dashboard";
import { EquipmentMasterList } from "@/pages/EquipmentMasterList";
import { NewEquipmentPage, EditEquipmentPage } from "@/pages/EquipmentMaster";
import { SettingsPage } from "@/pages/Settings";
import { VibrationAnalysisPage } from "@/pages/VibrationAnalysis";
import { SensorDataPage } from "@/pages/SensorData";
import { LoginPage } from "@/pages/Login";
import { UnauthorizedPage } from "@/pages/Unauthorized";
import { ChangePasswordPage } from "@/pages/ChangePassword";
import { ALL_ROLES, WRITE_ROLES, ADMIN_ROLES } from "@/lib/role-access";

export default function App() {
  return (
    <ThemeProvider>
      <LayoutProvider>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/unauthorized" element={<UnauthorizedPage />} />

              <Route
                path="/change-password"
                element={
                  <ProtectedRoute>
                    <ChangePasswordPage />
                  </ProtectedRoute>
                }
              />

              <Route
                element={
                  <ProtectedRoute>
                    <AppShell />
                  </ProtectedRoute>
                }
              >
                <Route
                  path="/"
                  element={
                    <ProtectedRoute roles={[...ALL_ROLES]}>
                      <Dashboard />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/equipment"
                  element={
                    <ProtectedRoute roles={[...ALL_ROLES]}>
                      <EquipmentMasterList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/equipment/new"
                  element={
                    <ProtectedRoute roles={[...WRITE_ROLES]}>
                      <NewEquipmentPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/equipment/:id/edit"
                  element={
                    <ProtectedRoute roles={[...WRITE_ROLES]}>
                      <EditEquipmentPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/analysis"
                  element={
                    <ProtectedRoute roles={[...ALL_ROLES]}>
                      <VibrationAnalysisPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/sensor-data"
                  element={
                    <ProtectedRoute roles={[...ALL_ROLES]}>
                      <SensorDataPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/settings"
                  element={
                    <ProtectedRoute roles={[...ADMIN_ROLES]}>
                      <SettingsPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </LayoutProvider>
    </ThemeProvider>
  );
}
