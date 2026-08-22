import React, { useState, useRef, useEffect } from "react";
import { X, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { inputBase } from "./FormField";

interface MultiSelectProps {
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  error?: boolean;
}

export function MultiSelect({ options, value, onChange, placeholder = "Select...", error }: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggle = (option: string) => {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);
  };

  const remove = (option: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(value.filter((v) => v !== option));
  };

  return (
    <div ref={ref} className="relative">
      <div
        className={cn(
          inputBase,
          // Matches an empty TextInput exactly: 23px line-height + 12px x2 (py-3)
          // + 2px border = 49px. py-3 relaxes to py-g2 so chip rows stay compact.
          "min-h-[49px] py-g2 flex flex-wrap items-center gap-g1 cursor-pointer",
          "hover:border-signal-light/60",
          error && "border-destructive/50 bg-destructive/5",
          open && "border-signal-light ring-2 ring-[rgba(245,166,35,0.22)]"
        )}
        onClick={() => setOpen(!open)}
      >
        {value.length === 0 && <span className="text-placeholder font-normal py-0.5">{placeholder}</span>}
        {value.map((v) => (
          <span key={v} className="flex items-center gap-1 bg-warm text-brand text-sm font-medium px-2 py-0.5 rounded-md border border-signal-light/40">
            {v}
            <X size={10} className="cursor-pointer hover:text-brand-accent" onClick={(e) => remove(v, e)} />
          </span>
        ))}
        <ChevronDown size={14} className="ml-auto text-muted-foreground shrink-0" />
      </div>

      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-g1 bg-white border border-border rounded-lg shadow-card-hover max-h-52 overflow-y-auto">
          {options.map((opt) => (
            <div
              key={opt}
              className={cn(
                "flex items-center gap-g2 px-g3 py-g2 text-base cursor-pointer hover:bg-background transition-colors",
                value.includes(opt) && "bg-warm text-brand font-medium border-l-2 border-l-signal-dark"
              )}
              onClick={() => toggle(opt)}
            >
              <div className={cn("w-4 h-4 rounded border flex items-center justify-center", value.includes(opt) ? "bg-signal-dark border-signal-dark" : "border-border")}>
                {value.includes(opt) && (
                  <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M10 3L5 8.5 2 5.5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
                  </svg>
                )}
              </div>
              {opt}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
