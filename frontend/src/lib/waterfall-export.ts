/** CSV export of exactly what the waterfall is showing — spectra plus detected peaks. */
import type { WaterfallModel } from "./waterfall-adapter";
import type { WaterfallResponse } from "@/types/waterfall";

const HEADER = [
  "kind",
  "capture_number",
  "captured_at",
  "upload_id",
  "channel",
  "frequency_hz",
  "amplitude",
];

function escapeCell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function waterfallToCsv(model: WaterfallModel, meta: WaterfallResponse): string {
  const rows: string[] = [HEADER.join(",")];

  for (const line of model.lines) {
    const base = [line.captureNumber, line.capturedAt, line.uploadId, meta.channel];
    for (const [frequency, , amplitude] of line.points) {
      rows.push(["spectrum", ...base, frequency, amplitude].map(escapeCell).join(","));
    }
  }

  for (const peak of model.peaks) {
    const line = model.lines[peak.captureIndex];
    if (!line) continue;
    const [frequency, , amplitude] = peak.point;
    rows.push(
      [
        "peak",
        line.captureNumber,
        line.capturedAt,
        line.uploadId,
        meta.channel,
        frequency,
        amplitude,
      ]
        .map(escapeCell)
        .join(",")
    );
  }

  return rows.join("\n");
}

export function downloadWaterfallCsv(model: WaterfallModel, meta: WaterfallResponse): void {
  const csv = waterfallToCsv(model, meta);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `sensovibe-waterfall-ch${meta.channel + 1}-${model.lines.length}captures.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
