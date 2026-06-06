import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  delay?: number;
}

/** Enterprise card — white surface, subtle border, clean elevation */
export function GlassCard({
  children,
  className,
  hover = true,
  delay = 0,
}: GlassCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
      className={cn(
        "content-card transition-shadow duration-200",
        hover && "hover:shadow-card-hover",
        className
      )}
    >
      {children}
    </motion.div>
  );
}
