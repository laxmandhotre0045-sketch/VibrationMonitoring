import React from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
  /** Compact industrial dashboard label + spacing */
  compact?: boolean;
}

export function FormField({ label, required, error, hint, children, className, compact }: FormFieldProps) {
  return (
    <div className={cn("flex flex-col", compact ? "gap-1" : "gap-2", className)}>
      <label
        className={cn(
          compact
            ? "text-sm font-semibold uppercase tracking-wide text-muted-foreground"
            : "text-field-label"
        )}
      >
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {children}
      {hint && !error && (
        <div className="flex items-start gap-g2 px-g3 py-g2 bg-warm border border-border border-l-2 border-l-signal-light rounded-r-md">
          <Info size={14} className="text-signal-dark shrink-0 mt-0.5" />
          <p className="text-helper">{hint}</p>
        </div>
      )}
      {error && <p className="text-sm text-destructive font-medium">{error}</p>}
    </div>
  );
}

/** Canonical control geometry. Every field-sized control must use this so
 * they line up in a form row — see MultiSelect, which used to be 11px shorter. */
export const inputBase = cn(
  "w-full px-4 py-3 text-base font-normal rounded-lg transition-colors",
  "bg-white text-foreground border border-border",
  "placeholder:text-placeholder placeholder:font-normal",
  "focus:outline-none focus:border-signal-light focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]",
  "hover:border-border"
);

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  unit?: string;
  error?: boolean;
}

export function TextInput({ unit, error, className, ...props }: TextInputProps) {
  return (
    <div className="relative">
      <input
        className={cn(
          inputBase,
          error && "border-destructive/50 bg-destructive/5 focus:ring-destructive/15 focus:border-destructive",
          unit && "pr-16",
          className
        )}
        {...props}
      />
      {unit && (
        <span className="absolute right-4 top-1/2 -translate-y-1/2 text-base text-muted-foreground pointer-events-none">
          {unit}
        </span>
      )}
    </div>
  );
}

interface SelectInputProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: Array<string | number>;
  placeholder?: string;
  error?: boolean;
}

export function SelectInput({ options, placeholder, error, className, ...props }: SelectInputProps) {
  return (
    <select
      className={cn(
        inputBase,
        "appearance-none cursor-pointer",
        error && "border-destructive/50 bg-destructive/5",
        className
      )}
      {...props}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  );
}

interface TextareaInputProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export function TextareaInput({ error, className, ...props }: TextareaInputProps) {
  return (
    <textarea
      className={cn(
        inputBase,
        "resize-none",
        error && "border-destructive/50 bg-destructive/5",
        className
      )}
      {...props}
    />
  );
}

interface RangeInputProps {
  unit?: string;
  valueMin?: number | string;
  valueMax?: number | string;
  onChangeMin?: (v: string) => void;
  onChangeMax?: (v: string) => void;
  type?: string;
}

export function RangeInput({
  unit,
  valueMin,
  valueMax,
  onChangeMin,
  onChangeMax,
  type = "number",
}: RangeInputProps) {
  return (
    <div className="flex items-center gap-g3">
      <div className="relative flex-1">
        <input type={type} value={valueMin ?? ""} onChange={(e) => onChangeMin?.(e.target.value)} placeholder="Min" className={inputBase} />
        {unit && <span className="absolute right-4 top-1/2 -translate-y-1/2 text-base text-muted-foreground">{unit}</span>}
      </div>
      <span className="text-muted-foreground text-base">—</span>
      <div className="relative flex-1">
        <input type={type} value={valueMax ?? ""} onChange={(e) => onChangeMax?.(e.target.value)} placeholder="Max" className={inputBase} />
        {unit && <span className="absolute right-4 top-1/2 -translate-y-1/2 text-base text-muted-foreground">{unit}</span>}
      </div>
    </div>
  );
}
