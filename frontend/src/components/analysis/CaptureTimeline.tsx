import React, { useMemo, useState } from "react";
import { CalendarRange, ChevronLeft, ChevronRight, Files } from "lucide-react";
import type { SensorDataUpload } from "@/types/measurements";
import {
  formatCaptureSelection,
  formatRangeLabel,
  formatShortDayLabel,
  groupUploadsByDay,
  toDateKey,
} from "@/lib/upload-format";
import { cn } from "@/lib/utils";

export type DayFilter = "all" | string;

interface CaptureTimelineProps {
  files: SensorDataUpload[];
  /** Backend total for the active date range; null while loading. */
  totalFiles: number | null;
  fromDate: string;
  toDate: string;
  selectedFileId: string | null;
  selectedDay: DayFilter;
  onSelectDay: (day: DayFilter) => void;
  onSelectFile: (fileId: string) => void;
  isLoading?: boolean;
  className?: string;
}

import {
  analysisKpiClass,
  analysisKpiLabelClass,
  analysisKpiValueClass,
} from "./analysis-layout";

function SummaryStat({
  icon: Icon,
  label,
  value,
  loading = false,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  loading?: boolean;
}) {
  return (
    <div className={analysisKpiClass}>
      <div className={cn(analysisKpiLabelClass, "flex items-center gap-1")}>
        <Icon size={11} className="text-signal-dark shrink-0" aria-hidden />
        {label}
      </div>
      {loading ? (
        <p className={cn(analysisKpiValueClass, "text-muted-foreground animate-pulse")}>—</p>
      ) : (
        <p className={analysisKpiValueClass}>{value}</p>
      )}
    </div>
  );
}

export function CaptureTimeline({
  files,
  totalFiles,
  fromDate,
  toDate,
  selectedFileId,
  selectedDay,
  onSelectDay,
  onSelectFile,
  isLoading = false,
  className,
}: CaptureTimelineProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const dayGroups = useMemo(() => groupUploadsByDay(files), [files]);
  const dayKeys = useMemo(
    () => Array.from(dayGroups.keys()).sort((a, b) => a.localeCompare(b)),
    [dayGroups]
  );

  const visibleFiles = useMemo(() => {
    const sorted = [...files].sort((a, b) => a.created_at.localeCompare(b.created_at));
    if (selectedDay === "all") return sorted;
    return sorted.filter((f) => toDateKey(f.created_at) === selectedDay);
  }, [files, selectedDay]);

  const rangeStart = useMemo(
    () => new Date(`${fromDate}T00:00:00`).getTime(),
    [fromDate]
  );
  const rangeEnd = useMemo(
    () => new Date(`${toDate}T23:59:59.999`).getTime(),
    [toDate]
  );
  const rangeSpan = Math.max(rangeEnd - rangeStart, 1);

  const selectedFile = files.find((f) => f.id === selectedFileId) ?? null;
  const hoveredFile = hoveredId ? files.find((f) => f.id === hoveredId) ?? null : null;
  const hasData = totalFiles != null && totalFiles > 0;

  const selectedIndex = visibleFiles.findIndex((f) => f.id === selectedFileId);
  const canNavigate = visibleFiles.length > 1;
  const canGoPrev = canNavigate && selectedIndex > 0;
  const canGoNext = canNavigate && selectedIndex >= 0 && selectedIndex < visibleFiles.length - 1;

  const goToPrev = () => {
    if (!canGoPrev) return;
    onSelectFile(visibleFiles[selectedIndex - 1].id);
  };

  const goToNext = () => {
    if (!canGoNext && selectedIndex >= 0) return;
    if (selectedIndex < 0) {
      onSelectFile(visibleFiles[0].id);
      return;
    }
    onSelectFile(visibleFiles[selectedIndex + 1].id);
  };

  if (isLoading) {
    return (
      <div
        className={cn("rounded-md border border-border bg-surface/30 px-3 py-3", className)}
        aria-busy="true"
        aria-label="Loading capture timeline"
      >
        <div className="flex items-center gap-2 justify-center">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-cta" />
          <p className="text-sm text-muted-foreground">Loading uploads…</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-md border border-border bg-surface/30 px-3 py-2.5 space-y-2.5",
        className
      )}
    >
      {hasData && (
        <div className="flex flex-wrap gap-2">
          <SummaryStat
            icon={Files}
            label="Total Files in Range"
            value={totalFiles ?? 0}
            loading={totalFiles == null}
          />
          <SummaryStat
            icon={CalendarRange}
            label="Selected Date Range"
            value={formatRangeLabel(fromDate, toDate)}
          />
        </div>
      )}

      {hasData && (
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by day">
          <DayChip
            label="All"
            active={selectedDay === "all"}
            onClick={() => onSelectDay("all")}
          />
          {dayKeys.map((day) => (
            <DayChip
              key={day}
              label={formatShortDayLabel(day)}
              active={selectedDay === day}
              onClick={() => onSelectDay(day)}
            />
          ))}
        </div>
      )}

      {!hasData && totalFiles === 0 ? (
        <p className="text-sm text-muted-foreground py-2 text-center">
          No uploads found for the selected date range.
        </p>
      ) : visibleFiles.length === 0 && hasData ? (
        <p className="text-sm text-muted-foreground py-2 text-center">
          No captures on the selected day.
        </p>
      ) : (
        <div className="relative mx-0.5 pt-1 pb-g4">
          <div
            className="absolute left-0 right-0 top-4 h-px rounded-full bg-gradient-to-r from-signal-light/25 via-signal-light/70 to-signal-light/25"
            aria-hidden
          />
          <div className="relative h-8">
            {visibleFiles.map((file) => {
              const t = new Date(file.created_at).getTime();
              const pct = Math.min(100, Math.max(0, ((t - rangeStart) / rangeSpan) * 100));
              const isSelected = file.id === selectedFileId;

              return (
                <button
                  key={file.id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  title={formatCaptureSelection(file)}
                  onClick={() => onSelectFile(file.id)}
                  onMouseEnter={() => setHoveredId(file.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onFocus={() => setHoveredId(file.id)}
                  onBlur={() => setHoveredId(null)}
                  className={cn(
                    "absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition-all duration-200",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]",
                    isSelected
                      ? "h-4 w-4 border-cta bg-cta shadow-[0_0_0_4px_rgba(255,107,0,0.18)]"
                      : "h-3 w-3 border-signal-dark bg-white hover:h-3.5 hover:w-3.5 hover:border-cta",
                    file.parse_status === "failed" && !isSelected && "border-destructive/60"
                  )}
                  style={{ left: `${pct}%` }}
                />
              );
            })}
          </div>
          {hoveredFile && (
            <div
              className="pointer-events-none absolute left-1/2 top-10 z-20 -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-white px-2 py-1 text-xs font-medium text-muted-foreground shadow-sm"
              role="tooltip"
            >
              {formatCaptureSelection(hoveredFile)}
            </div>
          )}
        </div>
      )}

      {hasData && visibleFiles.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
          <p className={analysisKpiLabelClass}>File Navigation</p>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={goToPrev}
              disabled={!canGoPrev}
              aria-label="Previous capture"
              className={cn(
                "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-white transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]",
                canGoPrev
                  ? "text-foreground hover:border-signal-light hover:bg-warm"
                  : "cursor-not-allowed text-muted-foreground/40"
              )}
            >
              <ChevronLeft size={14} />
            </button>
            <span className="min-w-[4.5rem] text-center text-sm font-semibold text-foreground">
              {selectedIndex >= 0
                ? `${selectedIndex + 1} of ${visibleFiles.length}`
                : `— of ${visibleFiles.length}`}
            </span>
            <button
              type="button"
              onClick={goToNext}
              disabled={!canGoNext && selectedIndex >= 0 && selectedIndex >= visibleFiles.length - 1}
              aria-label="Next capture"
              className={cn(
                "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-white transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]",
                canGoNext || selectedIndex < 0
                  ? "text-foreground hover:border-signal-light hover:bg-warm"
                  : "cursor-not-allowed text-muted-foreground/40"
              )}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {hasData && (selectedFile || hoveredFile) && (
        <div className="rounded-md border border-border border-l-2 border-l-signal-light bg-white px-2.5 py-1.5">
          <p
            className={cn(
              "text-sm truncate leading-snug",
              selectedFile ? "font-medium text-foreground" : "text-muted-foreground"
            )}
            title={formatCaptureSelection(selectedFile ?? hoveredFile!)}
          >
            {formatCaptureSelection(selectedFile ?? hoveredFile!)}
          </p>
        </div>
      )}
    </div>
  );
}

function DayChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-sm font-semibold transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(255,107,0,0.45)]",
        active
          ? "border-cta bg-cta text-cta-foreground"
          : "border-border bg-white text-muted-foreground hover:border-signal-light hover:text-foreground"
      )}
    >
      {label}
    </button>
  );
}
