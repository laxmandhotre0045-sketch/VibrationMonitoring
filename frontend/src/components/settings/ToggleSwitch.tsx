import React from "react";
import { cn } from "@/lib/utils";

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  id?: string;
}

export function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
  label,
  id,
}: ToggleSwitchProps) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "inline-flex items-center gap-2",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
      )}
    >
      <span className="relative inline-flex h-6 w-11 shrink-0">
        <input
          id={id}
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span
          className={cn(
            "absolute inset-0 rounded-full border transition-colors duration-200",
            "border-border bg-muted peer-focus-visible:ring-2 peer-focus-visible:ring-signal-light/45",
            "peer-checked:border-machine-healthy/40 peer-checked:bg-machine-healthy/20"
          )}
          aria-hidden
        />
        <span
          className={cn(
            "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200",
            "border border-border peer-checked:translate-x-5 peer-checked:border-machine-healthy/50"
          )}
          aria-hidden
        />
      </span>
      {label && <span className="text-sm font-medium text-foreground">{label}</span>}
    </label>
  );
}
