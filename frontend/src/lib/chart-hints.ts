import type { PlotType } from "@/types/measurements";

const HINTS: Record<PlotType, string> = {
  time_waveform:
    "Scroll to zoom time axis · Drag to pan · Double-click to reset · Y-axis stays fixed",
  circular_time_waveform:
    "Scroll to zoom · Drag to pan · Double-click to reset · Y-axis stays fixed",
  fft_spectrum:
    "Scroll to zoom frequency axis · Drag to pan · Y-axis stays fixed",
  envelope_spectrum:
    "Scroll to zoom frequency axis · Drag to pan · Y-axis stays fixed",
  trend_plot:
    "Scroll to zoom time axis · Drag to pan · Y-axis stays fixed",
};

export function chartHintFor(plotType: PlotType): string {
  return HINTS[plotType];
}

export function autoscaleTitleFor(plotType: PlotType): string {
  if (plotType === "fft_spectrum" || plotType === "envelope_spectrum") {
    return "Autoscale frequency axis — fit all data";
  }
  if (plotType === "time_waveform" || plotType === "trend_plot") {
    return "Autoscale time axis — fit all data";
  }
  return "Autoscale axis — fit all data";
}
