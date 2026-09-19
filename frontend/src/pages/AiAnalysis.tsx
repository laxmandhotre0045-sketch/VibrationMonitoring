import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ChevronRight, Network, Sparkles } from "lucide-react";

import { listSensors, fetchSensorExport } from "@/api/sensorExport";
import { listThresholdRules } from "@/api/thresholds";
import { getDashboardSummary } from "@/api/dashboard";
import { useLayout } from "@/contexts/LayoutContext";
import { ALL_PLANTS } from "@/components/layout/nav-config";
import { PageHero } from "@/components/layout/PageHero";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import {
  analysisCardPad,
  analysisChannelBtnClass,
  analysisPageStack,
} from "@/components/analysis/analysis-layout";
import { HierarchyFilterBar } from "@/components/ai/HierarchyFilterBar";
import { HierarchyTree } from "@/components/ai/HierarchyTree";
import { AiHealthScoreCard } from "@/components/ai/AiHealthScoreCard";
import { FaultFindingsCard } from "@/components/ai/FaultFindingsCard";
import { AnomalyTimelineCard } from "@/components/ai/AnomalyTimelineCard";
import { TrendForecastCard } from "@/components/ai/TrendForecastCard";
import {
  assessHealth,
  buildAiDataset,
  channelSeries,
  diagnoseCapture,
  resolveAbsoluteLimits,
  scoreAnomalies,
} from "@/lib/ai-diagnostics";
import {
  buildSensorHierarchy,
  EMPTY_SELECTION,
  normalizeSelection,
  resolvePath,
  sameSelection,
  selectLevel,
  selectionForSensor,
  type HierarchyLevel,
  type HierarchySelection,
} from "@/lib/sensor-hierarchy";
import { cn } from "@/lib/utils";

/**
 * AI Analysis.
 *
 * Navigation is the asset hierarchy — Plant → Area → Line → Machine → Sensor —
 * as a cascading filter bar and as a browsable tree, the two sharing one model
 * so they cannot disagree about what exists.
 *
 * Once a sensor is chosen the page reads its full feature export and runs the
 * diagnostic rules in `@/lib/ai-diagnostics` over it: a condition score, the
 * fault patterns the latest capture matches, per-capture novelty, and where the
 * trend is heading. Those rules sit on the same features the Status (Health)
 * tab grades rather than a separate model service, so the two screens can never
 * disagree about a machine.
 */
export function AiAnalysisPage() {
  const { selectedPlant } = useLayout();
  const plantFilter = selectedPlant === ALL_PLANTS ? undefined : selectedPlant;

  const [selection, setSelection] = useState<HierarchySelection>(EMPTY_SELECTION);
  const [channel, setChannel] = useState(0);

  const sensorsQuery = useQuery({
    queryKey: ["ai-analysis", "sensors"],
    queryFn: () => listSensors(),
  });

  // The fleet summary is what grades each machine; the sensor list only says
  // where things are. The tree needs both.
  const summaryQuery = useQuery({
    queryKey: ["ai-analysis", "summary", plantFilter ?? "all"],
    queryFn: () => getDashboardSummary(plantFilter),
  });

  const hierarchy = useMemo(() => {
    const all = sensorsQuery.data ?? [];
    const scoped = plantFilter ? all.filter((s) => s.plant_name === plantFilter) : all;
    return buildSensorHierarchy(scoped, summaryQuery.data?.equipment_health ?? []);
  }, [sensorsQuery.data, summaryQuery.data, plantFilter]);

  // Drop anything the tree no longer contains — a plant switch, a refetch — and
  // walk down through the levels that offer only one choice.
  useEffect(() => {
    setSelection((prev) => {
      const next = normalizeSelection(hierarchy, prev);
      return sameSelection(prev, next) ? prev : next;
    });
  }, [hierarchy]);

  const path = useMemo(() => resolvePath(hierarchy, selection), [hierarchy, selection]);
  const selectedSensor = path.sensor?.sensor ?? null;
  const sensorId = selection.sensorId;

  const handleSelect = (level: HierarchyLevel, value: string) => {
    setSelection((prev) => normalizeSelection(hierarchy, selectLevel(prev, level, value)));
    setChannel(0);
  };

  const handleSelectSensor = (id: string) => {
    const next = selectionForSensor(hierarchy, id);
    if (next) {
      setSelection(next);
      setChannel(0);
    }
  };

  const exportQuery = useQuery({
    queryKey: ["ai-analysis", "export", sensorId],
    queryFn: () => fetchSensorExport(sensorId),
    enabled: Boolean(sensorId),
  });

  const thresholdQuery = useQuery({
    queryKey: ["ai-analysis", "thresholds"],
    queryFn: () => listThresholdRules(),
  });

  const dataset = useMemo(
    () => buildAiDataset(exportQuery.data?.rows ?? []),
    [exportQuery.data]
  );

  // Channel 0 does not always exist — a sensor whose first channel is 1 would
  // otherwise land on an empty analysis.
  const activeChannel = dataset.channels.includes(channel) ? channel : (dataset.channels[0] ?? 0);

  const analysis = useMemo(() => {
    const series = channelSeries(dataset, activeChannel);
    if (!series.length) return null;

    const latest = series[series.length - 1];
    const history = series.slice(0, -1);
    const findings = diagnoseCapture(latest, history);
    const anomalies = scoreAnomalies(series);
    const assessment = assessHealth(latest, findings, anomalies[anomalies.length - 1] ?? null);

    return { series, latest, history, findings, anomalies, assessment };
  }, [dataset, activeChannel]);

  const limits = useMemo(
    () =>
      resolveAbsoluteLimits(
        thresholdQuery.data?.items ?? [],
        activeChannel,
        selectedSensor?.machine_type ?? null
      ),
    [thresholdQuery.data, activeChannel, selectedSensor]
  );

  const breadcrumb = [
    path.plant?.label,
    path.area?.label,
    path.line?.label,
    path.machine?.label,
    path.sensor?.label,
  ].filter((part): part is string => Boolean(part));

  return (
    <div className={analysisPageStack}>
      <PageHero
        title="AI Analysis"
        subtitle="Automated fault diagnosis, anomaly detection and trend projection across a sensor's full capture history."
        vibrationBg
        breadcrumbs={[{ label: "Home", href: "/" }, { label: "AI Analysis" }]}
      />

      <GlassCard className={analysisCardPad} delay={0.04}>
        <AnalysisSectionHeader
          icon={Network}
          title="Asset Hierarchy"
          subtitle="Narrow down to one measurement point. Each level offers only what the level above it contains."
        />

        <HierarchyFilterBar
          hierarchy={hierarchy}
          selection={selection}
          onSelect={handleSelect}
        />

        {(breadcrumb.length > 0 || dataset.channels.length > 1) && (
          <div className="mt-g3 flex flex-wrap items-center justify-between gap-g3 border-t border-border pt-g3">
            {breadcrumb.length > 0 && (
              <nav
                aria-label="Selected asset path"
                className="flex min-w-0 flex-wrap items-center gap-1 text-sm"
              >
                {breadcrumb.map((part, index) => (
                  <React.Fragment key={`${part}-${index}`}>
                    {index > 0 && (
                      <ChevronRight size={13} className="text-muted-foreground" aria-hidden />
                    )}
                    <span
                      className={cn(
                        index === breadcrumb.length - 1
                          ? "font-bold text-brand"
                          : "text-muted-foreground"
                      )}
                    >
                      {part}
                    </span>
                  </React.Fragment>
                ))}
              </nav>
            )}

            {dataset.channels.length > 1 && (
              <div className="flex items-center gap-g2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Channel
                </span>
                <div className="flex gap-1 rounded-md border border-border bg-white p-1">
                  {dataset.channels.map((ch) => (
                    <button
                      key={ch}
                      type="button"
                      onClick={() => setChannel(ch)}
                      className={cn(
                        analysisChannelBtnClass,
                        ch === activeChannel
                          ? "bg-brand text-white"
                          : "text-muted-foreground hover:bg-warm hover:text-brand"
                      )}
                    >
                      CH{ch}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </GlassCard>

      <HierarchyTree
        hierarchy={hierarchy}
        selection={selection}
        onSelectSensor={handleSelectSensor}
      />

      {sensorsQuery.isError && (
        <GlassCard className="flex items-center gap-g2 p-g4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          Could not load the sensor list.
        </GlassCard>
      )}

      {exportQuery.isError && (
        <GlassCard className="flex items-center gap-g2 p-g4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          Could not load the capture history for this sensor.
        </GlassCard>
      )}

      {!sensorId && (
        <GlassCard className={analysisCardPad} delay={0.08}>
          <div className="flex flex-col items-center py-g6 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#FFA500]/10 text-[#FFA500]">
              <Sparkles size={24} aria-hidden />
            </span>
            <h2 className="mt-g3 text-base font-bold text-foreground">Select a sensor to analyse</h2>
            <p className="mt-g1 max-w-md text-sm text-muted-foreground">
              Pick one from the hierarchy above. The diagnosis runs on features already extracted
              from its uploaded captures — no separate configuration and nothing to train.
            </p>
          </div>
        </GlassCard>
      )}

      {sensorId && exportQuery.isLoading && (
        <GlassCard className={analysisCardPad} delay={0.08}>
          <p className="py-g5 text-center text-sm text-muted-foreground">
            Reading the capture history…
          </p>
        </GlassCard>
      )}

      {sensorId && !exportQuery.isLoading && !exportQuery.isError && !analysis && (
        <GlassCard className={analysisCardPad} delay={0.08}>
          <div className="flex flex-col items-center py-g6 text-center">
            <h2 className="text-base font-bold text-foreground">Nothing to analyse yet</h2>
            <p className="mt-g1 max-w-md text-sm text-muted-foreground">
              This sensor has no captures with extracted features. Upload data for it on the
              Vibration Analysis page and the diagnosis will appear here.
            </p>
          </div>
        </GlassCard>
      )}

      {analysis && (
        <>
          <AiHealthScoreCard
            assessment={analysis.assessment}
            capturesAnalyzed={analysis.series.length}
            observedAt={analysis.latest.observedAt}
          />
          <FaultFindingsCard
            findings={analysis.findings}
            hasHistory={analysis.history.length >= 2}
          />
          <AnomalyTimelineCard points={analysis.anomalies} />
          <TrendForecastCard series={analysis.series} limits={limits} />
        </>
      )}
    </div>
  );
}
