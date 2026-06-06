import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "warning";
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  icon,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  const variants = {
    primary: "btn-cta",
    secondary: "btn-cta-outline",
    ghost:
      "text-muted-foreground hover:text-brand hover:bg-muted rounded-full",
    danger:
      "bg-destructive text-white hover:bg-destructive/90 rounded-full shadow-sm",
    warning: "btn-cta",
  };

  const sizes = {
    sm: "px-4 py-1.5 text-xs gap-1.5",
    md: "px-5 py-2 text-sm gap-2",
    lg: "px-6 py-2.5 text-sm gap-2",
  };

  return (
    <motion.button
      whileTap={{ scale: disabled ? 1 : 0.98 }}
      transition={{ duration: 0.15 }}
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center font-semibold transition-all duration-200",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)] focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed",
        variants[variant],
        sizes[size],
        className
      )}
      {...(props as React.ComponentProps<typeof motion.button>)}
    >
      {icon}
      {children}
    </motion.button>
  );
}
