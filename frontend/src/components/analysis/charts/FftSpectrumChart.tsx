import React, { memo, useCallback, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
import type { PlotSeries } from "@/types/measurements";
import { useEchartsResize } from "@/hooks/useEchartsResize";
import { buildFftSpectrumOption } from "@/lib/fft-spectrum-option";
import { ChartContainer } from "./ChartContainer";

interface FftSpectrumChartProps {
  plot: PlotSeries;
  height?: number;
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

  useEchartsResize(getInstance, [plot, height]);

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
      onAutoscale={handleAutoscale}
      onReset={handleReset}
      onExport={handleExport}
      onChartResize={handleResize}
    >
      {({ height: chartHeight }) => (
        <ReactECharts
          ref={chartRef}
          option={option}
          notMerge
          lazyUpdate
          style={{ width: "100%", height: chartHeight }}
          opts={{ renderer: "canvas" }}
        />
      )}
    </ChartContainer>
  );
}

/** Enterprise FFT spectrum chart — Apache ECharts implementation. */
export const FftSpectrumChart = memo(FftSpectrumChartInner);
