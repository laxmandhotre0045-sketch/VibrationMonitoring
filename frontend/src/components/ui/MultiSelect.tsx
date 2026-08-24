import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { createPortal } from "react-dom";
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
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) setPosition({ top: rect.bottom + 4, left: rect.left, width: rect.width });
  }, []);

  useLayoutEffect(() => {
    if (open) updatePosition();
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!triggerRef.current?.contains(target) && !dropdownRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    // The dropdown is portaled to <body>, so reposition (rather than clip) when
    // an ancestor scrolls or the viewport resizes — capture:true catches scroll
    // on any nested scroll container, not just the window.
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, updatePosition]);

  const toggle = (option: string) => {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);
  };

  const remove = (option: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(value.filter((v) => v !== option));
  };

  return (
    <div ref={triggerRef} className="relative">
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

      {open &&
        createPortal(
          <div
            ref={dropdownRef}
            style={{ position: "fixed", top: position.top, left: position.left, width: position.width }}
            className="z-50 bg-white border border-border rounded-lg shadow-card-hover max-h-52 overflow-y-auto"
          >
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
          </div>,
          document.body
        )}
    </div>
  );
}
