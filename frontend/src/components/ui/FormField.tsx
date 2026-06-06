import React from "react";
import { cn } from "@/lib/utils";

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}

export function FormField({ label, required, error, hint, children, className }: FormFieldProps) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label className="text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-gray-400">{hint}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  unit?: string;
  error?: boolean;
}

export function TextInput({ unit, error, className, ...props }: TextInputProps) {
  return (
    <div className="relative">
      <input
        className={cn(
          "w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all",
          error ? "border-red-400 bg-red-50" : "border-gray-300 hover:border-gray-400",
          unit && "pr-12",
          className
        )}
        {...props}
      />
      {unit && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">
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
        "w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all appearance-none cursor-pointer",
        error ? "border-red-400 bg-red-50" : "border-gray-300 hover:border-gray-400",
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
        "w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all resize-none",
        error ? "border-red-400 bg-red-50" : "border-gray-300 hover:border-gray-400",
        className
      )}
      {...props}
    />
  );
}

interface RangeInputProps {
  labelMin?: string;
  labelMax?: string;
  unit?: string;
  valueMin?: number | string;
  valueMax?: number | string;
  onChangeMin?: (v: string) => void;
  onChangeMax?: (v: string) => void;
  error?: string;
  type?: string;
}

export function RangeInput({ unit, valueMin, valueMax, onChangeMin, onChangeMax, type = "number" }: RangeInputProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <input
          type={type}
          value={valueMin ?? ""}
          onChange={(e) => onChangeMin?.(e.target.value)}
          placeholder="Min"
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 hover:border-gray-400"
        />
        {unit && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">{unit}</span>
        )}
      </div>
      <span className="text-gray-400 text-sm font-medium">—</span>
      <div className="relative flex-1">
        <input
          type={type}
          value={valueMax ?? ""}
          onChange={(e) => onChangeMax?.(e.target.value)}
          placeholder="Max"
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 hover:border-gray-400"
        />
        {unit && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">{unit}</span>
        )}
      </div>
    </div>
  );
}
