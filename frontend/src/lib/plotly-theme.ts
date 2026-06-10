import type { Config, Layout, Shape } from "plotly.js";

/** SensoVibe diagnostic chart brand tokens */
export const PLOTLY_BRAND = {
  blue: "#15366D",
  amber: "#D98C00",
  orange: "#FF6B00",
  grid: "#F0EBE3",
  axis: "#E8E4DE",
  paper: "#FFFFFF",
  plot: "#FFFDF8",
  muted: "#5C6B7A",
  font: "Inter, system-ui, sans-serif",
} as const;

export const PLOTLY_TRACE = {
  line: { color: PLOTLY_BRAND.blue, width: 1.5 },
  marker: { color: PLOTLY_BRAND.amber, size: 4 },
  fill: "tozeroy" as const,
  fillcolor: "rgba(217, 140, 0, 0.12)",
};

const baseAxis = {
  showgrid: true,
  gridcolor: PLOTLY_BRAND.grid,
  gridwidth: 1,
  zeroline: false,
  linecolor: PLOTLY_BRAND.axis,
  linewidth: 1,
  tickfont: { family: PLOTLY_BRAND.font, size: 12, color: PLOTLY_BRAND.muted },
  titlefont: { family: PLOTLY_BRAND.font, size: 13, color: PLOTLY_BRAND.blue },
};

export function createPlotLayout(
  xLabel: string,
  yLabel: string,
  options?: {
    height?: number;
    yRange?: [number, number];
    shapes?: Partial<Shape>[];
  }
): Partial<Layout> {
  const layout: Partial<Layout> = {
    autosize: true,
    height: options?.height ?? 280,
    font: { family: PLOTLY_BRAND.font, size: 13, color: PLOTLY_BRAND.blue },
    paper_bgcolor: PLOTLY_BRAND.paper,
    plot_bgcolor: PLOTLY_BRAND.plot,
    margin: { l: 56, r: 20, t: 12, b: 52 },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: PLOTLY_BRAND.plot,
      bordercolor: PLOTLY_BRAND.amber,
      font: { family: PLOTLY_BRAND.font, size: 13, color: PLOTLY_BRAND.blue },
    },
    xaxis: {
      ...baseAxis,
      title: { text: xLabel, standoff: 8 },
      autorange: true,
      fixedrange: false,
    },
    yaxis: {
      ...baseAxis,
      title: { text: yLabel, standoff: 8 },
      autorange: false,
      fixedrange: true,
      ...(options?.yRange ? { range: options.yRange } : {}),
    },
    showlegend: false,
    shapes: options?.shapes,
  };

  return layout;
}

export const PLOTLY_CONFIG: Partial<Config> = {
  responsive: true,
  displaylogo: false,
  scrollZoom: "x",
  displayModeBar: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "zoom2d"],
  toImageButtonOptions: {
    format: "png",
    filename: "sensovibe-diagnostic-plot",
    height: 600,
    width: 900,
  },
};
