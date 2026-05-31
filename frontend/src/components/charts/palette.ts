// Categorical data-viz palette, sourced from theme tokens in index.css so charts
// stay consistent and adapt to light/dark. SVG `fill` accepts var() in modern browsers.
export const CHART_PALETTE = [
  "var(--ph-chart-1)",
  "var(--ph-chart-2)",
  "var(--ph-chart-3)",
  "var(--ph-chart-4)",
  "var(--ph-chart-5)",
  "var(--ph-chart-6)",
] as const;

export function chartColor(index: number): string {
  return CHART_PALETTE[index % CHART_PALETTE.length];
}
