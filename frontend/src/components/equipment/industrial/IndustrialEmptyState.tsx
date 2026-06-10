import React from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface IndustrialEmptyStateProps {
  message: string;
  className?: string;
}

export function IndustrialEmptyState({ message, className }: IndustrialEmptyStateProps) {
  return (
    <div className={cn("flex items-start gap-3 px-4 py-3 bg-background border border-border border-l-2 border-l-brand-accent rounded-lg", className)}>
      <AlertCircle size={16} className="text-brand-accent-dark shrink-0 mt-0.5" />
      <p className="text-helper">{message}</p>
    </div>
  );
}
