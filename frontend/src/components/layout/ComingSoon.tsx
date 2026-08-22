import React from "react";
import { motion } from "framer-motion";
import { ArrowRight, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHero } from "./PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { pageStack } from "@/lib/layout";

interface ComingSoonProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  features?: string[];
}

export function ComingSoon({ title, subtitle, icon: Icon, features = [] }: ComingSoonProps) {
  return (
    <div className={pageStack}>
      <PageHero title={title} subtitle={subtitle} breadcrumbs={[{ label: "Home", href: "/" }, { label: title }]} />

      <GlassCard className="card-pad text-center">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="flex flex-col items-center max-w-lg mx-auto"
        >
          <div className="w-16 h-16 rounded-xl bg-white border border-border flex items-center justify-center mb-g3">
            <Icon size={36} className="text-signal-dark" />
          </div>

          <h2 className="text-section-title mb-g1">Coming Soon</h2>
          <div className="brand-divider mb-g3" />
          <p className="text-helper mb-g4">
            This module is under development and will be available in an upcoming release.
          </p>

          {features.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-g2 w-full mb-g4">
              {features.map((feature) => (
                <div key={feature} className="px-g3 py-g2 rounded-lg bg-warm border border-border text-sm font-medium text-brand/90 text-left">
                  {feature}
                </div>
              ))}
            </div>
          )}

          <Link to="/equipment">
            <Button icon={<ArrowRight size={16} />}>Go to Equipment Master</Button>
          </Link>
        </motion.div>
      </GlassCard>
    </div>
  );
}
