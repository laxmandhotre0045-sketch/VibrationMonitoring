import { useEffect } from "react";
import Plotly from "plotly.js-dist-min";

/** Resize Plotly when the container or viewport changes (e.g. fullscreen). Preserves zoom/pan. */
export function usePlotlyResize(
  getGraph: () => Plotly.PlotlyHTMLElement | null,
  chartHeight: number,
  deps: unknown[] = []
) {
  useEffect(() => {
    const resize = () => {
      const graph = getGraph();
      if (!graph) return;
      Plotly.relayout(graph, { height: chartHeight }).then(() => {
        Plotly.Plots.resize(graph);
      });
    };

    resize();
    window.addEventListener("resize", resize);

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => resize())
        : null;

    const container = getGraph()?.parentElement;
    if (observer && container) {
      observer.observe(container);
    }

    return () => {
      window.removeEventListener("resize", resize);
      observer?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartHeight, ...deps]);
}
