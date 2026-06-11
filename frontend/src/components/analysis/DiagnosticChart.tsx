import React, { memo, useCallback, useMemo, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import type { PlotSeries } from "@/types/measurements";
import { createThresholdShapes, getPlotThresholds } from "@/lib/chart-thresholds";
import { createPlotLayout, PLOTLY_CONFIG } from "@/lib/plotly-theme";
import { plotSeriesLayoutOptions, plotSeriesToTrace } from "@/lib/plotly-data";
import { withGeneratedTimeAxis } from "@/lib/waveform-time-axis";
import { usePlotlyResize } from "@/hooks/usePlotlyResize";
import { autoscaleTitleFor, chartHintFor } from "@/lib/chart-hints";
import { ChartContainer } from "./charts/ChartContainer";
import { FftSpectrumChart } from "./charts/FftSpectrumChart";

const Plot = createPlotlyComponent(Plotly);

interface DiagnosticChartProps {
  plot: PlotSeries;
  height?: number;
  /** Plot-config sampling rate (Hz) — used to derive time waveform X-axis on the frontend. */
  samplingRateHz?: number;
}

function PlotlyDiagnosticChart({ plot, height = 280, samplingRateHz }: DiagnosticChartProps) {
  const graphRef = useRef<Plotly.PlotlyHTMLElement | null>(null);
  const baseLayoutRef = useRef<Partial<Plotly.Layout> | null>(null);

  const displayPlot = useMemo(
    () => withGeneratedTimeAxis(plot, samplingRateHz),
    [plot, samplingRateHz]
  );

  const trace = useMemo(() => plotSeriesToTrace(displayPlot), [displayPlot]);

  const baseLayout = useMemo(() => {
    const { yRange, xTickFormat, xTickSuffix } = plotSeriesLayoutOptions(displayPlot);
    const thresholds = getPlotThresholds(displayPlot);
    const layout = createPlotLayout(displayPlot.x_label, displayPlot.y_label, {
      height,
      yRange,
      shapes: createThresholdShapes(thresholds),
      xTickFormat,
      xTickSuffix,
    });
    baseLayoutRef.current = layout;
    return layout;
  }, [displayPlot, height]);

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
    if (!graphRef.current || !baseLayoutRef.current) return;
    const currentHeight = graphRef.current.layout?.height;
    Plotly.relayout(graphRef.current, {
      ...baseLayoutRef.current,
      ...(typeof currentHeight === "number" ? { height: currentHeight } : {}),
    });
  }, []);

  const handleExport = useCallback(() => {
    if (!graphRef.current) return;
    Plotly.downloadImage(graphRef.current, {
      format: "png",
      filename: `sensovibe-${plot.plot_type}-ch${plot.channel}`,
      height: 480,
      width: 800,
    });
  }, [plot.plot_type, plot.channel]);

  const getGraph = useCallback(() => graphRef.current, []);

  return (
    <ChartContainer
      title={plot.title}
      channel={plot.channel}
      height={height}
      hint={chartHintFor(plot.plot_type)}
      autoscaleTitle={autoscaleTitleFor(plot.plot_type)}
      onAutoscale={handleAutoscale}
      onReset={handleReset}
      onExport={handleExport}
    >
      {({ height: chartHeight, isFullscreen }) => (
        <PlotlyChartViewport
          trace={trace}
          baseLayout={baseLayout}
          chartHeight={chartHeight}
          config={config}
          revision={revision}
          getGraph={getGraph}
          isFullscreen={isFullscreen}
          onInitialized={handleInitialized}
        />
      )}
    </ChartContainer>
  );
}

interface PlotlyChartViewportProps {
  trace: ReturnType<typeof plotSeriesToTrace>;
  baseLayout: Partial<Plotly.Layout>;
  chartHeight: number;
  config: Partial<Plotly.Config>;
  revision: number;
  getGraph: () => Plotly.PlotlyHTMLElement | null;
  isFullscreen: boolean;
  onInitialized: (_: unknown, graphDiv: Readonly<HTMLElement>) => void;
}

function PlotlyChartViewport({
  trace,
  baseLayout,
  chartHeight,
  config,
  revision,
  getGraph,
  isFullscreen,
  onInitialized,
}: PlotlyChartViewportProps) {
  usePlotlyResize(getGraph, chartHeight, [isFullscreen, revision]);

  return (
    <Plot
      data={[trace]}
      layout={{ ...baseLayout, height: chartHeight, autosize: true }}
      config={config}
      revision={revision}
      onInitialized={onInitialized}
      onUpdate={onInitialized}
      useResizeHandler
      className="w-full rounded-lg overflow-hidden"
      style={{ width: "100%", height: chartHeight }}
    />
  );
}

function DiagnosticChartInner({ plot, height = 280, samplingRateHz }: DiagnosticChartProps) {
  if (plot.plot_type === "fft_spectrum") {
    return <FftSpectrumChart plot={plot} height={height} />;
  }
  return <PlotlyDiagnosticChart plot={plot} height={height} samplingRateHz={samplingRateHz} />;
}

/** Enterprise diagnostic chart — routes FFT to ECharts, other plots to Plotly. */
export const DiagnosticChart = memo(DiagnosticChartInner);
