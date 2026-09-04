import React, { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { AlignJustify, Box, CircleDot, Compass, Move3D, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Loaded on demand — the waterfall pulls in echarts-gl (WebGL) and the vector
 * and orbit views their own chart code, none of which the waveform section
 * needs. Keeping the lazy boundaries here preserves the code-splitting these
 * views had as top-level tabs.
 */
const WaterfallTab = React.lazy(() =>
  import("./WaterfallTab").then((m) => ({ default: m.WaterfallTab }))
);
const VectorTab = React.lazy(() =>
  import("./VectorTab").then((m) => ({ default: m.VectorTab }))
);
const OrbitTab = React.lazy(() =>
  import("./OrbitTab").then((m) => ({ default: m.OrbitTab }))
);
const MigrationTab = React.lazy(() =>
  import("./MigrationTab").then((m) => ({ default: m.MigrationTab }))
);
const RawWaveformTab = React.lazy(() =>
  import("./RawWaveformTab").then((m) => ({ default: m.RawWaveformTab }))
);

export type AdvancedPlotId =
  | "waterfall"
  | "cascade"
  | "vector"
  | "orbit"
  | "migration"
  | "raw";

const ADVANCED_PLOTS: {
  id: AdvancedPlotId;
  label: string;
  icon: LucideIcon;
  loading: string;
}[] = [
  { id: "waterfall", label: "3D Waterfall", icon: Box, loading: "Loading 3D waterfall…" },
  { id: "cascade", label: "2D Cascade", icon: AlignJustify, loading: "Loading 2D cascade…" },
  { id: "vector", label: "Vibration Vector", icon: Compass, loading: "Loading vibration vector…" },
  { id: "orbit", label: "Casing Orbit", icon: CircleDot, loading: "Loading casing orbit…" },
  { id: "migration", label: "1X Amplitude Migration", icon: Move3D, loading: "Calculating 1× response…" },
  { id: "raw", label: "Raw Data", icon: Radio, loading: "Loading raw data…" },
];

interface AdvancedPlotsSectionProps {
  sensorId: string;
  channelCount: number;
  activeChannel: number;
  selectedUploadId: string;
  className?: string;
}

/**
 * The six advanced diagnostics, one at a time.
 *
 * Each of these mounts its own query — the waterfall pulls dozens of spectra,
 * the migration view recomputes 1× across every capture — so they render only
 * while selected rather than all together. Every view is the existing tab
 * component, unchanged; this is the selector that used to be the top-level tab
 * bar, moved down a level.
 *
 * Nothing is selected until the user picks a view. Detailed Analysis is the
 * landing tab and stays mounted, so preselecting one would put its fetch and
 * its chart bundle (echarts-gl, for the waterfall) on every page load — cost
 * these views did not carry as tabs the user had to open.
 */
export function AdvancedPlotsSection({
  sensorId,
  channelCount,
  activeChannel,
  selectedUploadId,
  className,
}: AdvancedPlotsSectionProps) {
  const [active, setActive] = useState<AdvancedPlotId | null>(null);
  const current = ADVANCED_PLOTS.find((plot) => plot.id === active);

  return (
    <div className={cn("space-y-g3", className)}>
      <div
        className="overflow-x-auto scrollbar-thin -mx-1 px-1"
        role="tablist"
        aria-label="Advanced plots and diagnostics"
      >
        <div className="inline-flex w-full flex-wrap gap-1 rounded-lg border border-border bg-[#F5F3EF] p-1">
          {ADVANCED_PLOTS.map((plot) => {
            const Icon = plot.icon;
            const isActive = active === plot.id;

            return (
              <button
                key={plot.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActive(plot.id)}
                className={cn(
                  "inline-flex h-9 flex-1 items-center justify-center gap-1.5 whitespace-nowrap",
                  "min-w-[132px] rounded-md px-3 text-sm font-semibold transition-all duration-200",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-light/45",
                  isActive
                    ? "bg-white text-signal-dark shadow-sm ring-1 ring-signal-light/35"
                    : "text-muted-foreground hover:bg-white/70 hover:text-foreground"
                )}
              >
                <Icon size={15} strokeWidth={isActive ? 2.25 : 2} aria-hidden />
                {plot.label}
              </button>
            );
          })}
        </div>
      </div>

      {!current && (
        <p className="text-sm text-muted-foreground">
          Select a diagnostic view above to load it.
        </p>
      )}

      <React.Suspense
        fallback={<p className="text-sm text-muted-foreground">{current?.loading}</p>}
      >
        {active === "waterfall" && (
          <WaterfallTab
            view="waterfall"
            sensorId={sensorId}
            channelCount={channelCount}
            defaultChannel={activeChannel}
          />
        )}
        {active === "cascade" && (
          <WaterfallTab
            view="cascade"
            sensorId={sensorId}
            channelCount={channelCount}
            defaultChannel={activeChannel}
          />
        )}
        {active === "vector" && (
          <VectorTab
            selectedUploadId={selectedUploadId}
            sensorId={sensorId}
            channelCount={channelCount}
            defaultChannel={activeChannel}
          />
        )}
        {active === "orbit" && (
          <OrbitTab
            selectedUploadId={selectedUploadId}
            sensorId={sensorId}
            channelCount={channelCount}
          />
        )}
        {active === "migration" && (
          <MigrationTab sensorId={sensorId} channelCount={channelCount} />
        )}
        {active === "raw" && <RawWaveformTab sensorId={sensorId} />}
      </React.Suspense>
    </div>
  );
}
