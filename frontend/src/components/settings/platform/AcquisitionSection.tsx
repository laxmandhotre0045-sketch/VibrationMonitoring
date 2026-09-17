import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Cable,
  Calculator,
  Loader2,
  Save,
  Sliders,
  Waves,
} from "lucide-react";
import { getEquipment, listEquipment } from "@/api/equipment";
import { getAcquisitionConfig, saveAcquisitionConfig } from "@/api/acquisition";
import { Button } from "@/components/ui/Button";
import { FormField, TextInput } from "@/components/ui/FormField";
import { SettingsSectionCard } from "@/components/settings/SettingsSectionCard";
import { analysisSelectClass } from "@/components/analysis/analysis-layout";
import { FFT_WINDOWS } from "@/types/measurements";
import {
  CHANNEL_AXES,
  CHANNEL_SIGNAL_TYPES,
  type AcquisitionConfig,
  type AcquisitionConfigUpdate,
  type ChannelAxis,
  type ChannelMapEntry,
  type ChannelSignalType,
} from "@/types/acquisition";
import type { EquipmentOut } from "@/types/equipment";
import { cn } from "@/lib/utils";

/**
 * Everything the DAQ form edits. Numeric fields allow "" so a half-typed value
 * does not snap back to a default under the user's cursor.
 */
interface AcquisitionForm {
  ksps: number | "";
  fmaxHz: number | "";
  lor: number | "";
  windowType: string;
  averageCount: number | "";
  overlapPercentage: number | "";
  totalChannelCount: number | "";
  sensitivityMvPerG: number | "";
  collectionIntervalMinutes: number | "";
  channelMap: ChannelMapEntry[];
}

const NUMBER_FIELD = "py-2 px-3 text-base h-10";

/**
 * Mirrors backend signal_processing.SAMPLES_PER_LINE.
 *
 * LOR counts spectral lines from DC to Nyquist, so L lines need 2L samples and
 * Δf = Fs / (2·LOR). Dividing by LOR alone would report twice the real
 * resolution and disagree with the JSON the device receives. A portable
 * analyser that instead defines LOR up to Fmax reports Δf = Fmax/LOR — that
 * figure is shown separately below, not substituted here.
 */
const SAMPLES_PER_LINE = 2;

/** Backend limits, repeated so a message can name the real bound. */
const LIMITS = {
  lorMin: 64,
  lorMax: 65536,
  averagingMax: 256,
  overlapMax: 95,
  channelMax: 32,
  intervalMax: 1440,
} as const;

/** Below this, a mV/g figure is a placeholder rather than hardware data. */
const MIN_PLAUSIBLE_SENSITIVITY = 1;

function numberOrEmpty(value: string): number | "" {
  if (value === "") return "";
  const n = Number(value);
  return Number.isFinite(n) ? n : "";
}

function isPositive(value: number | ""): value is number {
  return value !== "" && value > 0;
}

function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 1) return `${(seconds * 1000).toPrecision(4)} ms`;
  return `${seconds.toPrecision(4)} s`;
}

/**
 * FastAPI returns `detail` as a string for our explicit HTTPExceptions but as an
 * array of `{loc, msg}` for schema validation failures. Surface the first real
 * message either way rather than a generic "Save failed".
 */
function readErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail.find(
      (item): item is { msg: string } =>
        !!item && typeof (item as { msg?: unknown }).msg === "string"
    );
    if (first) return first.msg.replace(/^Value error, /, "");
  }
  return "Save failed";
}

function formToState(config: AcquisitionConfig): AcquisitionForm {
  return {
    ksps: config.ksps,
    fmaxHz: config.fmaxHz,
    lor: config.lor,
    windowType: config.windowType,
    averageCount: config.averageCount,
    overlapPercentage: config.overlapPercentage,
    totalChannelCount: config.totalChannelCount,
    sensitivityMvPerG: config.sensitivityMvPerG ?? "",
    collectionIntervalMinutes: config.collectionIntervalMinutes,
    channelMap: config.channelMap,
  };
}

/** One titled panel inside the settings card. */
function Block({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-white p-g3">
      <header className="mb-g3 flex items-start gap-2.5">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/[0.05] text-brand/60">
          {icon}
        </span>
        <div>
          <h3 className="text-sm font-bold text-brand">{title}</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

function ReadOut({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-bold text-brand">{value}</p>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function AcquisitionSection() {
  const queryClient = useQueryClient();
  const [equipmentId, setEquipmentId] = useState("");
  const [sensorId, setSensorId] = useState("");
  const [form, setForm] = useState<AcquisitionForm | null>(null);
  /**
   * Which sensor the current form was seeded from. Without this the seeding
   * effect re-runs on every refetch — including the one a successful save
   * triggers — which would wipe the "Saved" confirmation and discard any edits
   * made while a background refresh was in flight.
   */
  const [formSensorId, setFormSensorId] = useState("");
  const [saved, setSaved] = useState(false);

  const equipmentList = useQuery({
    queryKey: ["equipment-list-acquisition"],
    queryFn: () => listEquipment({ page: 1, page_size: 100 }),
  });

  const equipment = useQuery({
    queryKey: ["equipment-detail", equipmentId],
    queryFn: () => getEquipment(equipmentId),
    enabled: !!equipmentId,
  });

  const config = useQuery({
    queryKey: ["acquisition-config", sensorId],
    queryFn: () => getAcquisitionConfig({ sensorId }),
    enabled: !!sensorId,
    retry: false,
  });

  const sensors = (equipment.data as EquipmentOut | undefined)?.sensors ?? [];

  // Seed the form once per sensor from whatever the API reports, including the
  // defaults it applies to a sensor that has never been configured. Later
  // refetches do not reseed — a successful save pushes the stored values back
  // into the form itself.
  useEffect(() => {
    if (!sensorId) {
      setForm(null);
      setFormSensorId("");
      return;
    }
    if (!config.data || formSensorId === sensorId) return;
    setForm(formToState(config.data));
    setFormSensorId(sensorId);
    setSaved(false);
  }, [sensorId, config.data, formSensorId]);

  const sampleRateHz = form && isPositive(form.ksps) ? form.ksps * 1000 : 0;
  const channelCount = form && isPositive(form.totalChannelCount) ? form.totalChannelCount : 0;

  /**
   * Live read-outs, using the same formula as
   * services/acquisition_config.compute_acquisition_formula so the page can
   * never disagree with the JSON the device receives.
   */
  const derived = useMemo(() => {
    if (!form || sampleRateHz <= 0 || !isPositive(form.lor)) return null;
    const lor = form.lor;
    const samplesPerBlock = lor * SAMPLES_PER_LINE;
    const resolution = sampleRateHz / samplesPerBlock;
    const blockTime = samplesPerBlock / sampleRateHz;
    const averages = isPositive(form.averageCount) ? form.averageCount : 1;
    const overlap = form.overlapPercentage === "" ? 0 : form.overlapPercentage;
    const step = Math.trunc(samplesPerBlock * (1 - overlap / 100));
    const nyquist = sampleRateHz / 2;
    const effectiveFmax = isPositive(form.fmaxHz) ? form.fmaxHz : nyquist;

    return {
      resolution,
      blockTime,
      samplesPerBlock,
      totalTime: blockTime * averages,
      stepSamples: step > 0 ? step : samplesPerBlock,
      nyquist,
      // Analyser-style view of the same settings, shown for reconciliation only.
      linesBelowFmax: Math.trunc(effectiveFmax / resolution) + 1,
      fmaxResolution: effectiveFmax / lor,
      fmaxBlockTime: lor / effectiveFmax,
    };
  }, [form, sampleRateHz]);

  /** Field-level validation, mirroring the backend's rules. */
  const errors = useMemo(() => {
    const e: Partial<Record<keyof AcquisitionForm, string>> = {};
    if (!form) return e;

    if (!isPositive(form.ksps)) e.ksps = "Must be greater than 0";

    if (!isPositive(form.fmaxHz)) {
      e.fmaxHz = "Must be greater than 0";
    } else if (sampleRateHz > 0 && form.fmaxHz > sampleRateHz / 2) {
      e.fmaxHz = `Above Nyquist (${(sampleRateHz / 2).toLocaleString()} Hz)`;
    }

    if (!isPositive(form.lor)) {
      e.lor = "Must be greater than 0";
    } else if (form.lor < LIMITS.lorMin || form.lor > LIMITS.lorMax) {
      e.lor = `Must be between ${LIMITS.lorMin} and ${LIMITS.lorMax.toLocaleString()}`;
    }

    if (!isPositive(form.averageCount)) {
      e.averageCount = "Must be at least 1";
    } else if (form.averageCount > LIMITS.averagingMax) {
      e.averageCount = `Maximum ${LIMITS.averagingMax}`;
    }

    if (form.overlapPercentage === "" || form.overlapPercentage < 0) {
      e.overlapPercentage = "Must be 0 or more";
    } else if (form.overlapPercentage > LIMITS.overlapMax) {
      e.overlapPercentage = `Maximum ${LIMITS.overlapMax}%`;
    }

    if (!isPositive(form.totalChannelCount)) {
      e.totalChannelCount = "Must be at least 1";
    } else if (form.totalChannelCount > LIMITS.channelMax) {
      e.totalChannelCount = `Maximum ${LIMITS.channelMax}`;
    }

    if (!isPositive(form.sensitivityMvPerG)) e.sensitivityMvPerG = "Must be greater than 0";

    if (!isPositive(form.collectionIntervalMinutes)) {
      e.collectionIntervalMinutes = "Must be at least 1 minute";
    } else if (form.collectionIntervalMinutes > LIMITS.intervalMax) {
      e.collectionIntervalMinutes = `Maximum ${LIMITS.intervalMax} minutes (24 h)`;
    }



    return e;
  }, [form, sampleRateHz]);

  const hasErrors = Object.keys(errors).length > 0;

  // A stored sensitivity far below any real accelerometer is a placeholder. Say
  // so rather than letting it silently scale every amplitude in the platform.
  const sensitivitySuspect =
    !!form &&
    isPositive(form.sensitivityMvPerG) &&
    form.sensitivityMvPerG < MIN_PLAUSIBLE_SENSITIVITY;

  /**
   * Channel rows follow Channel Count, so raising it exposes new rows
   * immediately. Rows beyond the count stay in state but are not sent, so
   * lowering then raising the count again does not lose labels.
   */
  const channelRows = useMemo(() => {
    if (!form) return [] as ChannelMapEntry[];
    const byIndex = new Map(form.channelMap.map((c) => [c.channel_index, c]));
    return Array.from({ length: channelCount }, (_, i): ChannelMapEntry => {
      const index = i + 1;
      return (
        byIndex.get(index) ?? {
          channel_index: index,
          machine_axis: CHANNEL_AXES[i % CHANNEL_AXES.length],
          signal_type: "VIBRATION",
          label: null,
        }
      );
    });
  }, [form, channelCount]);

  const update = <K extends keyof AcquisitionForm>(key: K, value: AcquisitionForm[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setSaved(false);
  };

  const updateChannel = (index: number, patch: Partial<ChannelMapEntry>) => {
    setForm((f) => {
      if (!f) return f;
      const edited = channelRows.map((row) =>
        row.channel_index === index ? { ...row, ...patch } : row
      );
      // Keep rows above the current channel count so they survive a round trip.
      const beyond = f.channelMap.filter((c) => c.channel_index > channelCount);
      return { ...f, channelMap: [...edited, ...beyond] };
    });
    setSaved(false);
  };

  const save = useMutation({
    mutationFn: async () => {
      if (!form || !sensorId) return null;
      // Send ksps only — the backend derives sample_rate_hz from it and rejects
      // a payload where the two disagree.
      const payload: AcquisitionConfigUpdate = {
        sensor_id: sensorId,
        ksps: Number(form.ksps),
        fmax_hz: Number(form.fmaxHz),
        lor: Number(form.lor),
        window_type: form.windowType,
        average_count: Number(form.averageCount),
        overlap_percentage: Number(form.overlapPercentage),
        total_channel_count: Number(form.totalChannelCount),
        collection_interval_minutes: Number(form.collectionIntervalMinutes),
        sensitivity_mv_per_g: Number(form.sensitivityMvPerG),
        channel_map: channelRows.map((row) => ({
          channel_index: row.channel_index,
          machine_axis: row.machine_axis,
          signal_type: row.signal_type,
          label: row.label,
        })),
      };
      return saveAcquisitionConfig(payload);
    },
    onSuccess: (result) => {
      setSaved(true);
      if (result) setForm(formToState(result));
      queryClient.invalidateQueries({ queryKey: ["acquisition-config", sensorId] });
      // Sensitivity lives on the sensor record, so the equipment detail the
      // rest of the settings page reads is now stale.
      queryClient.invalidateQueries({ queryKey: ["equipment-detail", equipmentId] });
      queryClient.invalidateQueries({ queryKey: ["plot-config", sensorId] });
    },
  });

  const saveErrorMessage = save.isError
    ? readErrorDetail((save.error as { response?: { data?: { detail?: unknown } } })?.response?.data
        ?.detail)
    : null;

  return (
    <SettingsSectionCard
      icon={<Waves size={20} aria-hidden />}
      title="Acquisition & DAQ"
      description="Sample rate, FFT sizing and channel wiring for the selected sensor. The data collector reads these values from the platform."
    >
      <div className="space-y-g4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FormField label="Equipment" compact>
            <select
              className={analysisSelectClass}
              value={equipmentId}
              onChange={(e) => {
                setEquipmentId(e.target.value);
                setSensorId("");
              }}
            >
              <option value="">Select equipment…</option>
              {equipmentList.data?.items.map((eq) => (
                <option key={eq.id} value={eq.id}>
                  {eq.machine_name} — {eq.plant_name}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Sensor placement" compact>
            <select
              className={analysisSelectClass}
              value={sensorId}
              onChange={(e) => setSensorId(e.target.value)}
              disabled={!equipmentId}
            >
              <option value="">Select sensor…</option>
              {sensors.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.sensor_type} — {s.mounting_location} ({s.orientation})
                </option>
              ))}
            </select>
          </FormField>
        </div>

        {equipmentId && sensors.length === 0 && !equipment.isLoading && (
          <p className="rounded-lg border border-border bg-warm/40 px-4 py-3 text-sm text-muted-foreground">
            This machine has no sensors yet. Add one under Equipment Master first.
          </p>
        )}

        {sensorId && config.isLoading && (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-6">
            <Loader2 size={16} className="animate-spin text-brand" aria-hidden />
            <p className="text-sm text-muted-foreground">Loading acquisition settings…</p>
          </div>
        )}

        {sensorId && config.isError && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/[0.04] px-4 py-3 text-sm text-destructive">
            Could not load acquisition settings for this sensor.
          </p>
        )}

        {form && config.data && (
          <>
            {/* ── 1. Acquisition Configuration ─────────────────────────── */}
            <Block
              icon={<Sliders size={16} aria-hidden />}
              title="Acquisition Configuration"
              description="What the DAQ is told to capture. Sample Rate is derived from KSPS."
            >
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <FormField
                  label="KSPS"
                  compact
                  hint="Hardware rate — must match the DAQ"
                  error={errors.ksps}
                >
                  <TextInput
                    type="number"
                    min={1}
                    step="any"
                    className={NUMBER_FIELD}
                    value={form.ksps}
                    onChange={(e) => update("ksps", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField label="Sample Rate (Hz)" compact hint="KSPS × 1000">
                  <TextInput
                    type="number"
                    readOnly
                    className={cn(NUMBER_FIELD, "bg-warm/50 text-muted-foreground")}
                    value={sampleRateHz || ""}
                  />
                </FormField>

                <FormField
                  label="Fmax (Hz)"
                  compact
                  hint="Band of interest — must stay below Nyquist"
                  error={errors.fmaxHz}
                >
                  <TextInput
                    type="number"
                    min={1}
                    step="any"
                    className={NUMBER_FIELD}
                    value={form.fmaxHz}
                    onChange={(e) => update("fmaxHz", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField
                  label="LOR (FFT lines)"
                  compact
                  hint="Lines DC→Nyquist; block = 2 × LOR"
                  error={errors.lor}
                >
                  <TextInput
                    type="number"
                    min={LIMITS.lorMin}
                    max={LIMITS.lorMax}
                    className={NUMBER_FIELD}
                    value={form.lor}
                    onChange={(e) => update("lor", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField label="Window" compact hint="Applied by the edge DAQ">
                  <select
                    className={analysisSelectClass}
                    value={form.windowType}
                    onChange={(e) => update("windowType", e.target.value)}
                  >
                    {FFT_WINDOWS.map((w) => (
                      <option key={w} value={w}>
                        {w.charAt(0) + w.slice(1).toLowerCase()}
                      </option>
                    ))}
                  </select>
                </FormField>

                <FormField
                  label="Averaging"
                  compact
                  hint="1 = no averaging"
                  error={errors.averageCount}
                >
                  <TextInput
                    type="number"
                    min={1}
                    max={LIMITS.averagingMax}
                    className={NUMBER_FIELD}
                    value={form.averageCount}
                    onChange={(e) => update("averageCount", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField
                  label="Overlap (%)"
                  compact
                  hint={`0–${LIMITS.overlapMax}`}
                  error={errors.overlapPercentage}
                >
                  <TextInput
                    type="number"
                    min={0}
                    max={LIMITS.overlapMax}
                    className={NUMBER_FIELD}
                    value={form.overlapPercentage}
                    onChange={(e) => update("overlapPercentage", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField
                  label="Channel Count"
                  compact
                  hint="Drives the mapping rows below"
                  error={errors.totalChannelCount}
                >
                  <TextInput
                    type="number"
                    min={1}
                    max={LIMITS.channelMax}
                    className={NUMBER_FIELD}
                    value={form.totalChannelCount}
                    onChange={(e) => update("totalChannelCount", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField
                  label="Sensitivity (mV/g)"
                  compact
                  hint="Transducer hardware value"
                  error={errors.sensitivityMvPerG}
                >
                  <TextInput
                    type="number"
                    min={0}
                    step="any"
                    className={NUMBER_FIELD}
                    value={form.sensitivityMvPerG}
                    onChange={(e) => update("sensitivityMvPerG", numberOrEmpty(e.target.value))}
                  />
                </FormField>

                <FormField
                  label="Collection Interval (min)"
                  compact
                  hint="Wait between captures"
                  error={errors.collectionIntervalMinutes}
                >
                  <TextInput
                    type="number"
                    min={1}
                    max={LIMITS.intervalMax}
                    className={NUMBER_FIELD}
                    value={form.collectionIntervalMinutes}
                    onChange={(e) =>
                      update("collectionIntervalMinutes", numberOrEmpty(e.target.value))
                    }
                  />
                </FormField>
              </div>

              {sensitivitySuspect && (
                <p className="mt-g3 flex items-start gap-2 rounded-lg border border-[#FFA500]/40 bg-[#FFA500]/[0.07] px-3 py-2.5 text-xs text-[#8A5200]">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
                  <span>
                    <strong>{form.sensitivityMvPerG} mV/g</strong> is far below any real
                    accelerometer — an IEPE unit is typically 10–1000 mV/g, commonly 100. This
                    looks like placeholder data. Enter the value printed on the transducer
                    calibration sheet.
                  </span>
                </p>
              )}

              <p className="mt-g3 text-xs text-muted-foreground leading-relaxed">
                <strong>Collection Interval</strong> is how often a new acquisition is taken. It is
                not the sample rate and not the FFT block time — a 2-minute interval with a 100 ms
                block means the device captures for 100 ms, then waits about 2 minutes.
              </p>
            </Block>

            {/* ── 2. Calculated Acquisition ────────────────────────────── */}
            <Block
              icon={<Calculator size={16} aria-hidden />}
              title="Calculated Acquisition"
              description="Derived from the settings above. Read-only."
            >
              {derived ? (
                <>
                  <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-warm/30 p-3 sm:grid-cols-3 lg:grid-cols-6">
                    <ReadOut
                      label="Δf resolution"
                      value={`${derived.resolution.toPrecision(4)} Hz`}
                      hint="Fs ÷ (2 × LOR)"
                    />
                    <ReadOut
                      label="Block time"
                      value={formatSeconds(derived.blockTime)}
                      hint="1 ÷ Δf"
                    />
                    <ReadOut
                      label="Samples / block"
                      value={derived.samplesPerBlock.toLocaleString()}
                      hint="2 × LOR"
                    />
                    <ReadOut
                      label="Total acquisition"
                      value={formatSeconds(derived.totalTime)}
                      hint="Block × averages"
                    />
                    <ReadOut
                      label="Step size"
                      value={derived.stepSamples.toLocaleString()}
                      hint="After overlap"
                    />
                    <ReadOut
                      label="Nyquist"
                      value={`${derived.nyquist.toLocaleString()} Hz`}
                      hint="Fs ÷ 2"
                    />
                  </div>

                  <div className="mt-g3 rounded-lg border border-dashed border-border bg-muted/[0.06] p-3">
                    <p className="text-[11px] font-semibold tracking-wide text-muted-foreground">
                      Portable-analyser view (Fmax-based LOR) — for comparison only
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <ReadOut
                        label="Lines below Fmax"
                        value={derived.linesBelowFmax.toLocaleString()}
                        hint="Of this platform's lines"
                      />
                      <ReadOut
                        label="Analyser Δf"
                        value={`${derived.fmaxResolution.toPrecision(4)} Hz`}
                        hint="Fmax ÷ LOR"
                      />
                      <ReadOut
                        label="Analyser block time"
                        value={formatSeconds(derived.fmaxBlockTime)}
                        hint="LOR ÷ Fmax"
                      />
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
                      Many portable analysers define LOR as lines up to Fmax, giving Δf = Fmax ÷
                      LOR. This platform defines LOR as lines up to Nyquist, so it computes Δf = Fs
                      ÷ (2 × LOR). Both are correct for their own convention — these figures are
                      shown so the two can be reconciled. Only the Nyquist-based values above are
                      used to compute spectra.
                    </p>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Enter a valid KSPS and LOR to see the derived values.
                </p>
              )}
            </Block>

            {/* ── 3. Channel Mapping ───────────────────────────────────── */}
            <Block
              icon={<Cable size={16} aria-hidden />}
              title="Channel Mapping"
              description={`Measurement direction for each of the ${channelCount} configured channels. Sent to the device and used to label incoming data.`}
            >
              {channelCount > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] border-separate border-spacing-y-1.5 text-sm">
                    <thead>
                      <tr className="text-left text-[11px] font-semibold tracking-wide text-muted-foreground">
                        <th className="w-20 pl-1">Channel</th>
                        <th className="w-40">Direction</th>
                        <th className="w-40">Signal type</th>
                        <th>Label (optional)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {channelRows.map((row) => (
                        <tr key={row.channel_index}>
                          <td className="pl-1 font-bold text-brand">CH{row.channel_index}</td>
                          <td className="pr-2">
                            <select
                              className={analysisSelectClass}
                              aria-label={`Channel ${row.channel_index} direction`}
                              value={row.machine_axis}
                              onChange={(e) =>
                                updateChannel(row.channel_index, {
                                  machine_axis: e.target.value as ChannelAxis,
                                })
                              }
                            >
                              {CHANNEL_AXES.map((axis) => (
                                <option key={axis} value={axis}>
                                  {axis.charAt(0) + axis.slice(1).toLowerCase()}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="pr-2">
                            <select
                              className={analysisSelectClass}
                              aria-label={`Channel ${row.channel_index} signal type`}
                              value={row.signal_type}
                              onChange={(e) =>
                                updateChannel(row.channel_index, {
                                  signal_type: e.target.value as ChannelSignalType,
                                })
                              }
                            >
                              {CHANNEL_SIGNAL_TYPES.map((type) => (
                                <option key={type} value={type}>
                                  {type.charAt(0) + type.slice(1).toLowerCase()}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <TextInput
                              className={NUMBER_FIELD}
                              placeholder={`e.g. DE bearing ${row.machine_axis.toLowerCase()}`}
                              aria-label={`Channel ${row.channel_index} label`}
                              value={row.label ?? ""}
                              onChange={(e) =>
                                updateChannel(row.channel_index, {
                                  label: e.target.value || null,
                                })
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Set a channel count above to map channels.
                </p>
              )}
            </Block>

            {/* ── 4. Identity used by the collector ────────────────────── */}
            <div className="grid grid-cols-1 gap-3 rounded-xl border border-border bg-warm/30 p-3 sm:grid-cols-2">
              <ReadOut
                label="Device ID"
                value={config.data.deviceId || 'Not set'}
                hint={config.data.deviceId ? 'Collector may fetch config with ?device_id=…' : 'Set the Device ID under Equipment Master'}
              />
              <ReadOut
                label="Platform sensor ID"
                value={config.data.platformSensorId}
                hint="Use for ?sensor_id=… and when posting captures"
              />
            </div>

            {/* ── Save ─────────────────────────────────────────────────── */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-white px-g3 py-g3">
              <p className="max-w-xl text-xs text-muted-foreground leading-relaxed">
                Saving updates the configuration the edge device reads from{" "}
                <code className="rounded bg-warm/60 px-1 py-0.5 text-[11px]">
                  GET /api/v1/acquisition/config
                </code>
                . Analysis of already-stored captures is unaffected.
              </p>
              <div className="flex items-center gap-3">
                {saved && !save.isPending && (
                  <span className="text-sm font-semibold text-machine-healthy">Saved</span>
                )}
                {saveErrorMessage && (
                  <span className="max-w-xs text-sm font-semibold text-destructive">
                    {saveErrorMessage}
                  </span>
                )}
                {hasErrors && !save.isPending && (
                  <span className="text-sm font-semibold text-destructive">
                    Fix the highlighted fields
                  </span>
                )}
                <Button
                  type="button"
                  icon={<Save size={15} />}
                  onClick={() => save.mutate()}
                  disabled={save.isPending || hasErrors}
                >
                  {save.isPending ? "Saving…" : "Save settings"}
                </Button>
              </div>
            </div>
          </>
        )}

        {!sensorId && (
          <p className="rounded-lg border border-dashed border-border bg-muted/10 px-4 py-6 text-center text-sm text-muted-foreground">
            Select an equipment and sensor placement to configure acquisition.
          </p>
        )}
      </div>
    </SettingsSectionCard>
  );
}
