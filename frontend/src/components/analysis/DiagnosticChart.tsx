import React, { memo, useCallback, useMemo, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import type { PlotSeries } from "@/types/measurements";
import { createThresholdShapes, getPlotThresholds } from "@/lib/chart-thresholds";
import { createPlotLayout, PLOTLY_CONFIG } from "@/lib/plotly-theme";
import { plotSeriesLayoutOptions, plotSeriesToTrace } from "@/lib/plotly-data";
import { FftSpectrumChart } from "./charts/FftSpectrumChart";
import { ChartHeader } from "./ChartHeader";
import { ChartToolbar } from "./charts/ChartToolbar";

const Plot = createPlotlyComponent(Plotly);

interface DiagnosticChartProps {
  plot: PlotSeries;
  height?: number;
}

function PlotlyDiagnosticChart({ plot, height = 280 }: DiagnosticChartProps) {
  const graphRef = useRef<Plotly.PlotlyHTMLElement | null>(null);

  const trace = useMemo(() => plotSeriesToTrace(plot), [plot]);
  const layout = useMemo(() => {
    const { yRange } = plotSeriesLayoutOptions(plot);
    const thresholds = getPlotThresholds(plot);
    return createPlotLayout(plot.x_label, plot.y_label, {
      height,
      yRange,
      shapes: createThresholdShapes(thresholds),
    });
  }, [plot, height]);

  const config = useMemo(
    () => ({
      ...PLOTLY_CONFIG,
      toImageButtonOptions: {
        ...PLOTLY_CONFIG.toImageButtonOptions,
        filename: `sensovibe-${plot.plot_type}-ch${plot.channel}`,
      },
    }),
    [plot.plot_type, plot.channel]
  );

  const revision = useMemo(
    () => plot.x.length + plot.channel * 10_000 + plot.plot_type.length,
    [plot.x.length, plot.channel, plot.plot_type]
  );

  const handleInitialized = useCallback((_: unknown, graphDiv: Readonly<HTMLElement>) => {
    graphRef.current = graphDiv as Plotly.PlotlyHTMLElement;
  }, []);

  const handleAutoscale = useCallback(() => {
    if (!graphRef.current) return;
    Plotly.relayout(graphRef.current, { "xaxis.autorange": true });
  }, []);

  const handleReset = useCallback(() => {
    if (!graphRef.current) return;
    Plotly.relayout(graphRef.current, layout);
  }, [layout]);

  const handleExport = useCallback(() => {
    if (!graphRef.current) return;
    Plotly.downloadImage(graphRef.current, {
      format: "png",
      filename: `sensovibe-${plot.plot_type}-ch${plot.channel}`,
      height: 480,
      width: 800,
    });
  }, [plot.plot_type, plot.channel]);

  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <ChartHeader title={plot.title} channel={plot.channel} className="mb-0 min-w-0 flex-1" />
        <ChartToolbar
          onAutoscale={handleAutoscale}
          onReset={handleReset}
          onExport={handleExport}
          autoscaleTitle="Autoscale time axis — fit all data"
        />
      </div>
      <Plot
        data={[trace]}
        layout={layout}
        config={config}
        revision={revision}
        onInitialized={handleInitialized}
        onUpdate={handleInitialized}
        useResizeHandler
        className="w-full rounded-lg overflow-hidden"
        style={{ width: "100%", minHeight: height }}
      />
      <p className="mt-2 text-helper text-sm">
        Scroll to zoom time axis · Drag to pan · Double-click to reset · Y-axis stays fixed
      </p>
    </div>
  );
}

function DiagnosticChartInner({ plot, height = 280 }: DiagnosticChartProps) {
  if (plot.plot_type === "fft_spectrum") {
    return <FftSpectrumChart plot={plot} height={height} />;
  }
  return <PlotlyDiagnosticChart plot={plot} height={height} />;
}

/** Enterprise diagnostic chart — routes FFT to ECharts, other plots to Plotly. */
export const DiagnosticChart = memo(DiagnosticChartInner);
