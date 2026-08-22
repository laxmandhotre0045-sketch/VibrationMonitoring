import React from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ShieldAlert, LogOut, LayoutDashboard } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { HeroIntelligenceBg } from "@/components/brand/HeroIntelligenceBg";

export function UnauthorizedPage() {
  const { logout } = useAuth();

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-background px-g4 py-g6 overflow-hidden">
      <HeroIntelligenceBg className="absolute inset-0 opacity-30" />

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="relative z-10 w-full max-w-lg"
      >
        <GlassCard className="card-pad text-center">
          <div className="w-20 h-20 rounded-xl bg-white border border-border flex items-center justify-center mx-auto mb-g4">
            <ShieldAlert size={36} className="text-signal-dark" />
          </div>

          <h1 className="text-2xl font-bold text-brand mb-g2">Access Restricted</h1>
          <div className="brand-divider mx-auto mb-g3" />
          <p className="text-base text-helper mb-g5">
            You do not have permission to access this area.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link to="/">
              <Button icon={<LayoutDashboard size={16} />}>Return to Dashboard</Button>
            </Link>
            <Button
              variant="secondary"
              icon={<LogOut size={16} />}
              onClick={() => logout()}
            >
              Sign Out
            </Button>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  );
}
