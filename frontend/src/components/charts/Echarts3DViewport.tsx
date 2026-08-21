import React, { useCallback } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsType } from "echarts";
// Side-effect import: registers grid3D / line3D / scatter3D on the shared echarts instance.
import "echarts-gl";
import { useEchartsResize } from "@/hooks/useEchartsResize";
import type { Echarts3DOption } from "@/lib/waterfall-3d-option";

interface Echarts3DViewportProps {
  option: Echarts3DOption;
  chartHeight: number;
  isFullscreen: boolean;
  chartRef: React.RefObject<ReactECharts>;
  onChartReady?: (instance: EChartsType) => void;
}

/**
 * WebGL viewport for echarts-gl charts.
 *
 * Deliberately separate from EchartsGraphViewport: that one drives 2D-only behaviour
 * (dataZoom ranges, adaptive line width) which does not apply to a 3D grid, and the
 * camera is driven imperatively here so React state changes never rebuild the scene.
 */
export function Echarts3DViewport({
  option,
  chartHeight,
  isFullscreen,
  chartRef,
  onChartReady,
}: Echarts3DViewportProps) {
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
      onChartReady={onChartReady}
    />
  );
}
