import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Download, Search, AlertCircle } from "lucide-react";

import {
  listSensors,
  fetchSensorExport,
  downloadSensorCsv,
  type SensorListItem,
} from "@/api/sensorExport";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

/** Columns worth showing on screen. The CSV download always carries all 27. */
const TABLE_COLUMNS: Array<{ key: string; label: string; numeric?: boolean }> = [
  { key: "observed_at", label: "Observed at" },
  { key: "channel", label: "Ch", numeric: true },
  { key: "feature_name", label: "Feature" },
  { key: "value", label: "Value", numeric: true },
  { key: "unit", label: "Unit" },
  { key: "status", label: "Status" },
  { key: "source", label: "Source" },
];

/**
 * Rendering tens of thousands of <tr> locks the tab up for no benefit - the
 * complete set is one click away in the CSV.
 */
const MAX_TABLE_ROWS = 500;

const STATUS_STYLES: Record<string, string> = {
  normal: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warning: "bg-amber-50 text-amber-700 border-amber-200",
  critical: "bg-red-50 text-red-700 border-red-200",
  no_baseline: "bg-slate-100 text-slate-600 border-slate-200",
};

function StatusPill({ status }: { status: string }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className={cn(
        "inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        STATUS_STYLES[status] ?? "bg-slate-100 text-slate-600 border-slate-200",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function sensorLabel(s: SensorListItem): string {
  return `${s.machine_name} — ${s.mounting_location} (${s.orientation}) · ${s.plant_name}`;
}

export function SensorDataPage() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [sensorId, setSensorId] = useState<string>("");
  const [downloading, setDownloading] = useState(false);

  const sensorsQuery = useQuery({
    queryKey: ["sensor-export", "sensors"],
    queryFn: () => listSensors(),
  });

  const sensors = sensorsQuery.data ?? [];

  const filtered = useMemo(() => {
    const terms = search.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return sensors;
    return sensors.filter((s) => {
      const hay = sensorLabel(s).toLowerCase() + " " + (s.machine_id ?? "").toLowerCase();
      return terms.every((t) => hay.includes(t));
    });
  }, [sensors, search]);

  const exportQuery = useQuery({
    queryKey: ["sensor-export", "data", sensorId],
    queryFn: () => fetchSensorExport(sensorId),
    enabled: Boolean(sensorId),
  });

  const summary = exportQuery.data?.summary;
  const rows = exportQuery.data?.rows ?? [];
  const shownRows = rows.slice(0, MAX_TABLE_ROWS);

  async function handleDownload() {
    if (!sensorId) return;
    setDownloading(true);
    try {
      await downloadSensorCsv(sensorId);
      showToast("CSV downloaded", "success");
    } catch {
      showToast("Could not download the CSV", "error");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <div className="rounded-lg border border-border bg-white p-2">
          <Database className="h-5 w-5 text-signal-dark" />
        </div>
        <div>
          <h1 className="text-xl font-semibold">Sensor Data</h1>
          <p className="text-sm text-muted-foreground">
            Every measurement recorded for one sensor, ready to review or export as CSV.
          </p>
        </div>
      </div>

      <GlassCard className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter sensors…"
              className="w-full rounded-md border border-border bg-white py-2 pl-9 pr-3 text-sm"
            />
          </div>

          <select
            value={sensorId}
            onChange={(e) => setSensorId(e.target.value)}
            className="min-w-[320px] flex-1 rounded-md border border-border bg-white px-3 py-2 text-sm"
            disabled={sensorsQuery.isLoading}
          >
            <option value="">
              {sensorsQuery.isLoading
                ? "Loading sensors…"
                : filtered.length
                  ? "Select a sensor…"
                  : "No sensors match"}
            </option>
            {filtered.map((s) => (
              <option key={s.sensor_id} value={s.sensor_id}>
                {sensorLabel(s)}
              </option>
            ))}
          </select>

          <Button
            onClick={handleDownload}
            disabled={!sensorId || downloading || !rows.length}
          >
            <Download className="mr-2 h-4 w-4" />
            {downloading ? "Preparing…" : "Download CSV"}
          </Button>
        </div>
      </GlassCard>

      {sensorsQuery.isError && (
        <GlassCard className="flex items-center gap-2 p-4 text-sm text-red-600">
          <AlertCircle className="h-4 w-4" />
          Could not load the sensor list.
        </GlassCard>
      )}

      {summary && (
        <div className="flex flex-wrap gap-3">
          <Stat label="Rows" value={summary.csv_rows} />
          <Stat
            label="Captures"
            value={
              summary.truncated
                ? `${summary.captures_exported} / ${summary.captures_available}`
                : summary.captures_exported
            }
          />
          <Stat label="Channels" value={summary.channels.length} />
          {Object.entries(summary.status_counts).map(([k, v]) => (
            <Stat key={k} label={k.replace(/_/g, " ")} value={v} />
          ))}
        </div>
      )}

      <GlassCard className="overflow-hidden p-0">
        {!sensorId ? (
          <p className="p-6 text-sm text-muted-foreground">
            Pick a sensor above to see its measurements.
          </p>
        ) : exportQuery.isLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading measurements…</p>
        ) : exportQuery.isError ? (
          <p className="p-6 text-sm text-red-600">Could not load this sensor's data.</p>
        ) : !rows.length ? (
          <p className="p-6 text-sm text-muted-foreground">
            This sensor has no measurements yet. Upload a capture for it first.
          </p>
        ) : (
          <>
            <div className="max-h-[60vh] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    {TABLE_COLUMNS.map((c) => (
                      <th
                        key={c.key}
                        className={cn(
                          "whitespace-nowrap border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
                          c.numeric ? "text-right" : "text-left",
                        )}
                      >
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shownRows.map((row, i) => (
                    <tr key={`${row.upload_id}-${row.channel}-${row.feature_code}-${i}`}>
                      {TABLE_COLUMNS.map((c) => {
                        const raw = (row as unknown as Record<string, unknown>)[c.key];
                        return (
                          <td
                            key={c.key}
                            className={cn(
                              "whitespace-nowrap border-b border-border px-3 py-1.5",
                              c.numeric && "text-right tabular-nums font-mono",
                            )}
                          >
                            {c.key === "status" ? (
                              <StatusPill status={String(raw ?? "")} />
                            ) : (
                              String(raw ?? "")
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
              {rows.length > shownRows.length
                ? `Showing the first ${shownRows.length} of ${rows.length} rows. The CSV contains all ${rows.length}, with all 27 columns.`
                : `${rows.length} rows · the CSV contains all 27 columns.`}
            </p>
          </>
        )}
      </GlassCard>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <GlassCard className="min-w-[110px] px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </GlassCard>
  );
}

export default SensorDataPage;
