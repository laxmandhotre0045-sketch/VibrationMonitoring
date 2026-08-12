import React from "react";
import { motion } from "framer-motion";
import { ArrowRight, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHero } from "./PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";

interface ComingSoonProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  features?: string[];
}

export function ComingSoon({ title, subtitle, icon: Icon, features = [] }: ComingSoonProps) {
  return (
    <div>
      <PageHero title={title} subtitle={subtitle} breadcrumbs={[{ label: "Home", href: "/" }, { label: title }]} />

      <GlassCard className="p-6 sm:p-8 lg:p-10 text-center" hover={false}>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="flex flex-col items-center max-w-lg mx-auto"
        >
          <div className="w-16 sm:w-20 h-16 sm:h-20 rounded-xl bg-white border border-border flex items-center justify-center mb-4 sm:mb-6">
            <Icon size={28} sm className="text-signal-dark" />
          </div>

          <h2 className="text-lg sm:text-xl font-bold text-brand mb-2">Coming Soon</h2>
          <div className="brand-divider mb-3 sm:mb-4" />
          <p className="text-xs sm:text-sm text-muted-foreground mb-6 sm:mb-8 leading-relaxed">
            This module is under development and will be available in an upcoming release.
          </p>

          {features.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full mb-6 sm:mb-8">
              {features.map((feature) => (
                <div key={feature} className="px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg bg-warm border border-border text-xs sm:text-sm text-brand/80 text-left">
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
