import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile sidebar backdrop */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 bg-black/50 z-40 md:hidden"
          />
        )}
      </AnimatePresence>

      {/* Sidebar - Hidden on mobile unless open */}
      <motion.div
        className="hidden md:flex md:w-auto flex-shrink-0"
        initial={false}
      >
        <Sidebar />
      </motion.div>

      {/* Mobile sidebar - Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            key="mobile-sidebar"
            initial={{ x: -320 }}
            animate={{ x: 0 }}
            exit={{ x: -320 }}
            transition={{ duration: 0.25 }}
            className="absolute left-0 top-0 z-50 md:hidden h-screen w-80"
          >
            <Sidebar onClose={() => setSidebarOpen(false)} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopNav onMenuClick={() => setSidebarOpen(!sidebarOpen)} menuOpen={sidebarOpen} />
        <main className="flex-1 overflow-y-auto page-bg">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="page-shell px-g3 sm:px-g4 lg:px-g5 py-g4 lg:py-g5"
          >
            <Outlet />
          </motion.div>
        </main>
      </div>
    </div>
  );
}
