import React, { memo, useCallback, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption, EChartsType } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { useEchartsResize } from "@/hooks/useEchartsResize";
import { autoscaleTitleFor, chartHintFor } from "@/lib/chart-hints";
import { buildFftSpectrumOption } from "@/lib/fft-spectrum-option";
import { ChartContainer } from "./ChartContainer";

interface FftSpectrumChartProps {
  plot: PlotSeries;
  height?: number;
}

interface EchartsViewportProps {
  chartRef: React.RefObject<ReactECharts>;
  option: EChartsOption;
  chartHeight: number;
  isFullscreen: boolean;
}

function EchartsViewport({ chartRef, option, chartHeight, isFullscreen }: EchartsViewportProps) {
  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    [chartRef]
  );

  useEchartsResize(getInstance, [chartHeight, isFullscreen, option]);

  return (
    <ReactECharts
      ref={chartRef}
      option={option}
      notMerge
      lazyUpdate
      style={{ width: "100%", height: chartHeight }}
      opts={{ renderer: "canvas" }}
    />
  );
}

function FftSpectrumChartInner({ plot, height = 280 }: FftSpectrumChartProps) {
  const chartRef = useRef<ReactECharts>(null);

  const option = useMemo(() => buildFftSpectrumOption(plot), [plot]);

  const getInstance = useCallback(
    () => chartRef.current?.getEchartsInstance() as EChartsType | undefined,
    []
  );

  const handleResize = useCallback(() => {
    const instance = getInstance();
    if (instance && !instance.isDisposed()) {
      instance.resize();
    }
  }, [getInstance]);

  const handleAutoscale = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    instance.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
  }, [getInstance]);

  const handleReset = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;
    instance.dispatchAction({ type: "restore" });
    instance.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
  }, [getInstance]);

  const handleExport = useCallback(() => {
    const instance = getInstance();
    if (!instance) return;

    const dataUrl = instance.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#FFFDF8",
    });

    const link = document.createElement("a");
    link.download = `sensovibe-${plot.plot_type}-ch${plot.channel}.png`;
    link.href = dataUrl;
    link.click();
  }, [getInstance, plot.plot_type, plot.channel]);

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
      onChartResize={handleResize}
    >
      {({ height: chartHeight, isFullscreen }) => (
        <EchartsViewport
          chartRef={chartRef}
          option={option}
          chartHeight={chartHeight}
          isFullscreen={isFullscreen}
        />
      )}
    </ChartContainer>
  );
}

/** Enterprise FFT spectrum chart — Apache ECharts implementation. */
export const FftSpectrumChart = memo(FftSpectrumChartInner);
