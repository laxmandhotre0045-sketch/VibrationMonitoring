import React from "react";
import { motion } from "framer-motion";
import { KeyRound, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";

export function ChangePasswordPage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-g4 py-g6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="w-full max-w-lg"
      >
        <GlassCard className="card-pad text-center">
          <div className="w-16 h-16 rounded-xl bg-white border border-border flex items-center justify-center mx-auto mb-g4">
            <KeyRound size={28} className="text-signal-dark" />
          </div>

          <h1 className="text-2xl font-bold text-brand mb-2">Password Change Required</h1>
          <div className="brand-divider mx-auto mb-4" />
          <p className="text-base text-helper mb-2">
            Your administrator requires a password change before you can access the platform.
          </p>
          {user && (
            <p className="text-sm text-muted-foreground mb-g4">
              Signed in as <span className="font-semibold text-brand">{user.email}</span>
            </p>
          )}
          <p className="text-sm text-muted-foreground mb-g5 px-2">
            Password change API is not yet available. Contact your administrator.
          </p>

          <Button
            variant="secondary"
            icon={<LogOut size={16} />}
            onClick={() => logout()}
          >
            Sign Out
          </Button>
        </GlassCard>
      </motion.div>
    </div>
  );
}
