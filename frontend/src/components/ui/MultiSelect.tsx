import React, { useState, useRef, useEffect } from "react";
import { X, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

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
    if (value.includes(option)) {
      onChange(value.filter((v) => v !== option));
    } else {
      onChange([...value, option]);
    }
  };

  const remove = (option: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(value.filter((v) => v !== option));
  };

  return (
    <div ref={ref} className="relative">
      <div
        className={cn(
          "min-h-[38px] w-full px-3 py-1.5 text-sm border rounded-lg bg-white cursor-pointer flex flex-wrap gap-1 items-center",
          error ? "border-red-400" : "border-gray-300 hover:border-gray-400",
          open && "ring-2 ring-blue-500 border-transparent"
        )}
        onClick={() => setOpen(!open)}
      >
        {value.length === 0 && (
          <span className="text-gray-400 py-0.5">{placeholder}</span>
        )}
        {value.map((v) => (
          <span
            key={v}
            className="flex items-center gap-1 bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded-full"
          >
            {v}
            <X size={10} className="cursor-pointer hover:text-blue-600" onClick={(e) => remove(v, e)} />
          </span>
        ))}
        <ChevronDown size={14} className="ml-auto text-gray-400 shrink-0" />
      </div>

      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {options.map((opt) => (
            <div
              key={opt}
              className={cn(
                "flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-blue-50 transition-colors",
                value.includes(opt) && "bg-blue-50 text-blue-700 font-medium"
              )}
              onClick={() => toggle(opt)}
            >
              <div
                className={cn(
                  "w-4 h-4 rounded border flex items-center justify-center",
                  value.includes(opt) ? "bg-blue-600 border-blue-600" : "border-gray-300"
                )}
              >
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
