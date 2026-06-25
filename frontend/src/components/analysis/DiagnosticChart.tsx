import React, { memo } from "react";
import type { PlotSeries } from "@/types/measurements";
import { EchartsDiagnosticChart } from "./charts/EchartsDiagnosticChart";

interface DiagnosticChartProps {
  plot: PlotSeries;
  height?: number;
  /** Plot-config sampling rate (Hz) — used to derive time waveform X-axis on the frontend. */
  samplingRateHz?: number;
}

function DiagnosticChartInner({ plot, height = 280, samplingRateHz }: DiagnosticChartProps) {
  return (
    <EchartsDiagnosticChart plot={plot} height={height} samplingRateHz={samplingRateHz} />
  );
}

/** Enterprise diagnostic chart — all plots use Apache ECharts. */
export const DiagnosticChart = memo(DiagnosticChartInner);
