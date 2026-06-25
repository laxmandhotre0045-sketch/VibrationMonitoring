import { format, parseISO } from "date-fns";
import type { SensorDataUpload } from "@/types/measurements";

export function getUploadFilename(upload: SensorDataUpload): string {
  if (upload.original_filename) return upload.original_filename;
  return `upload-${upload.id.slice(0, 8)}`;
}

export function formatCaptureDate(iso: string): string {
  try {
    return format(parseISO(iso), "EEE, MMM d, yyyy");
  } catch {
    return new Date(iso).toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }
}

export function formatCaptureTime(iso: string): string {
  try {
    return format(parseISO(iso), "hh:mm:ss a");
  } catch {
    return new Date(iso).toLocaleTimeString();
  }
}

export function formatCaptureSelection(upload: SensorDataUpload): string {
  return `${formatCaptureDate(upload.created_at)} · ${formatCaptureTime(upload.created_at)} · ${getUploadFilename(upload)}`;
}

export function formatShortDayLabel(dateKey: string): string {
  try {
    return format(parseISO(`${dateKey}T12:00:00`), "MMM d");
  } catch {
    return dateKey;
  }
}

export function formatRangeLabel(fromDate: string, toDate: string): string {
  try {
    const from = format(parseISO(`${fromDate}T12:00:00`), "MMM d, yyyy");
    const to = format(parseISO(`${toDate}T12:00:00`), "MMM d, yyyy");
    return from === to ? from : `${from} – ${to}`;
  } catch {
    return `${fromDate} – ${toDate}`;
  }
}

export function toDateKey(iso: string): string {
  return iso.slice(0, 10);
}

export function groupUploadsByDay(uploads: SensorDataUpload[]): Map<string, SensorDataUpload[]> {
  const map = new Map<string, SensorDataUpload[]>();
  for (const upload of uploads) {
    const key = toDateKey(upload.created_at);
    const list = map.get(key) ?? [];
    list.push(upload);
    map.set(key, list);
  }
  for (const [, list] of map) {
    list.sort((a, b) => a.created_at.localeCompare(b.created_at));
  }
  return map;
}
