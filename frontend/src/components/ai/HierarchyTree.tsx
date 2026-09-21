import React, { useEffect, useMemo, useState } from "react";
import { ChevronRight, Network } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { AnalysisSectionHeader } from "@/components/analysis/AnalysisSectionHeader";
import { analysisCardPad } from "@/components/analysis/analysis-layout";
import { STATUS_META } from "@/lib/alert-status";
import { STATUS_TONES, toneForHealthStatus } from "@/lib/status-box";
import { StatusBadge, StatusRail } from "@/components/ui/StatusBox";
import type { EquipmentHealthStatus } from "@/types/dashboard";
import {
  resolvePath,
  type HierarchySelection,
  type SensorHierarchy,
} from "@/lib/sensor-hierarchy";
import { cn } from "@/lib/utils";

/** Above this many branches, opening everything is a wall rather than a view. */
const AUTO_EXPAND_LIMIT = 25;

const LEGEND_ORDER: EquipmentHealthStatus[] = [
  "critical",
  "warning",
  "no_baseline",
  "normal",
  "no_data",
];

interface TreeRowProps {
  depth: number;
  label: string;
  meta?: string;
  status: EquipmentHealthStatus;
  expandable: boolean;
  expanded: boolean;
  selected?: boolean;
  onToggle?: () => void;
  onSelect?: () => void;
}

function TreeRow({
  depth,
  label,
  meta,
  status,
  expandable,
  expanded,
  selected = false,
  onToggle,
  onSelect,
}: TreeRowProps) {
  const statusMeta = STATUS_META[status];
  const tone = STATUS_TONES[toneForHealthStatus(status)];

  return (
    <div
      className={cn(
        "relative flex items-center gap-g2 overflow-hidden rounded-md py-1.5 pr-g2 transition-colors",
        tone.wash,
        selected && "ring-1 ring-signal-light/50",
        !selected && "hover:bg-warm"
      )}
      style={{ paddingLeft: `${depth * 18 + 16}px` }}
    >
      {/* The light source. A rail at a fixed left edge rather than at the row's
          own indent, so status reads as one scannable column down the tree
          instead of a staircase the eye has to follow inward. */}
      <StatusRail tone={toneForHealthStatus(status)} className="rounded-r-sm" />

      {expandable ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-brand"
        >
          <ChevronRight
            size={14}
            className={cn("transition-transform duration-200", expanded && "rotate-90")}
          />
        </button>
      ) : (
        <span className="h-5 w-5 shrink-0" aria-hidden />
      )}

      {onSelect ? (
        <button
          type="button"
          onClick={onSelect}
          className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-foreground hover:text-brand"
        >
          {label}
        </button>
      ) : (
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
          {label}
        </span>
      )}

      {meta && (
        <span className="hidden shrink-0 truncate text-xs text-muted-foreground sm:inline">
          {meta}
        </span>
      )}
      <StatusBadge tone={toneForHealthStatus(status)}>{statusMeta.label}</StatusBadge>
    </div>
  );
}

interface HierarchyTreeProps {
  hierarchy: SensorHierarchy;
  selection: HierarchySelection;
  onSelectSensor: (sensorId: string) => void;
}

/**
 * The browsable half of the hierarchy.
 *
 * The filter bar is faster once you know where you are going; this is for the
 * case the bar cannot serve — seeing which machine in the plant is the one
 * worth opening. Status rolls up, so a red dot on a plant means something under
 * it is red.
 */
export function HierarchyTree({ hierarchy, selection, onSelectSensor }: HierarchyTreeProps) {
  const containerIds = useMemo(() => {
    const ids: string[] = [];
    for (const plant of hierarchy.plants) {
      ids.push(plant.id);
      for (const area of plant.areas) {
        ids.push(area.id);
        for (const line of area.lines) {
          ids.push(line.id);
          for (const machine of line.machines) ids.push(machine.id);
        }
      }
    }
    return ids;
  }, [hierarchy]);

  const selectedPathIds = useMemo(() => {
    const path = resolvePath(hierarchy, selection);
    return [path.plant?.id, path.area?.id, path.line?.id, path.machine?.id].filter(
      (id): id is string => Boolean(id)
    );
  }, [hierarchy, selection]);

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  // A new tree (a different plant filter, a refetch) resets the view; without
  // this the expansion state would describe branches that no longer exist.
  useEffect(() => {
    setExpanded(
      new Set(containerIds.length <= AUTO_EXPAND_LIMIT ? containerIds : [])
    );
  }, [containerIds]);

  // Picking a sensor in the filter bar should reveal it here rather than leave
  // the tree pointing somewhere else.
  useEffect(() => {
    if (!selectedPathIds.length) return;
    setExpanded((prev) => {
      const missing = selectedPathIds.filter((id) => !prev.has(id));
      if (!missing.length) return prev;
      const next = new Set(prev);
      for (const id of missing) next.add(id);
      return next;
    });
  }, [selectedPathIds]);

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const isOpen = (id: string) => expanded.has(id);

  return (
    <GlassCard className={analysisCardPad} delay={0.06}>
      <AnalysisSectionHeader
        icon={Network}
        title="Plant / Area / Line / Machine / Sensor"
        subtitle="Browse the asset tree. Machine condition comes from the fleet summary and rolls up, so a flagged branch is visible from the top."
      />

      <div className="mb-g3 flex flex-wrap items-center gap-g2">
        {LEGEND_ORDER.map((status) => {
          const meta = STATUS_META[status];
          const count = hierarchy.statusCounts[status];
          return (
            <StatusBadge
              key={status}
              tone={toneForHealthStatus(status)}
              // A tally of zero is still worth listing — it says the tree was
              // checked for that state — but it should not read as a count.
              className={cn("gap-1.5", count === 0 && "opacity-45")}
            >
              {meta.label}
              <span className="rounded-sm bg-black/20 px-1 tabular-nums">{count}</span>
            </StatusBadge>
          );
        })}

        <div className="ml-auto flex items-center gap-g2">
          <button
            type="button"
            onClick={() => setExpanded(new Set())}
            className="rounded-full border border-border bg-white px-2.5 py-0.5 text-[11px] font-semibold text-muted-foreground hover:border-signal-light/55 hover:text-brand"
          >
            Collapse all
          </button>
          <button
            type="button"
            onClick={() => setExpanded(new Set(containerIds))}
            className="rounded-full border border-border bg-white px-2.5 py-0.5 text-[11px] font-semibold text-muted-foreground hover:border-signal-light/55 hover:text-brand"
          >
            Expand all
          </button>
        </div>
      </div>

      {!hierarchy.plants.length ? (
        <p className="rounded-lg border border-border bg-warm px-g4 py-g3 text-sm text-muted-foreground">
          No sensors are registered under the current plant filter.
        </p>
      ) : (
        <div className="max-h-[420px] overflow-y-auto rounded-lg border border-border bg-white py-g2">
          {hierarchy.plants.map((plant) => (
            <div key={plant.id}>
              <TreeRow
                depth={0}
                label={plant.label}
                meta={`${plant.areas.length} area${plant.areas.length === 1 ? "" : "s"}`}
                status={plant.status}
                expandable
                expanded={isOpen(plant.id)}
                onToggle={() => toggle(plant.id)}
              />
              {isOpen(plant.id) &&
                plant.areas.map((area) => (
                  <div key={area.id}>
                    <TreeRow
                      depth={1}
                      label={area.label}
                      meta={`${area.lines.length} line${area.lines.length === 1 ? "" : "s"}`}
                      status={area.status}
                      expandable
                      expanded={isOpen(area.id)}
                      onToggle={() => toggle(area.id)}
                    />
                    {isOpen(area.id) &&
                      area.lines.map((line) => (
                        <div key={line.id}>
                          <TreeRow
                            depth={2}
                            label={line.label}
                            meta={`${line.machines.length} machine${line.machines.length === 1 ? "" : "s"}`}
                            status={line.status}
                            expandable
                            expanded={isOpen(line.id)}
                            onToggle={() => toggle(line.id)}
                          />
                          {isOpen(line.id) &&
                            line.machines.map((machine) => (
                              <div key={machine.id}>
                                <TreeRow
                                  depth={3}
                                  label={
                                    machine.machineId
                                      ? `${machine.label} — ${machine.machineId}`
                                      : machine.label
                                  }
                                  meta={machine.machineType}
                                  status={machine.status}
                                  expandable
                                  expanded={isOpen(machine.id)}
                                  onToggle={() => toggle(machine.id)}
                                />
                                {isOpen(machine.id) &&
                                  machine.sensors.map((sensor) => (
                                    <TreeRow
                                      key={sensor.id}
                                      depth={4}
                                      label={sensor.label}
                                      meta={sensor.detail}
                                      status={sensor.status}
                                      expandable={false}
                                      expanded={false}
                                      selected={selection.sensorId === sensor.id}
                                      onSelect={() => onSelectSensor(sensor.id)}
                                    />
                                  ))}
                              </div>
                            ))}
                        </div>
                      ))}
                  </div>
                ))}
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
