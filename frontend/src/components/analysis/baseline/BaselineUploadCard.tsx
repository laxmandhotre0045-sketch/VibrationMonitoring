import React, { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileUp, Loader2, Trash2 } from "lucide-react";
import { uploadBaselineFile } from "@/api/baselines";
import type { Baseline } from "@/types/baseline";
import { Button } from "@/components/ui/Button";
import { analysisInputClass } from "@/components/analysis/analysis-layout";
import { cn } from "@/lib/utils";

interface BaselineUploadCardProps {
  sensorId: string;
  channelCount: number;
  canWrite: boolean;
  className?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function defaultBaselineName(file: File): string {
  const stem = file.name.replace(/\.[^./\\]+$/, "");
  return `Baseline ${stem}`.slice(0, 200);
}

/**
 * Direct baseline file upload.
 *
 * `POST /api/v1/baselines/upload` has been in the backend all along — the
 * frontend simply never called it, so the only route to a baseline was
 * promoting an existing capture from Detailed Analysis, and picking a baseline
 * file from disk was impossible. This is that endpoint's UI: choose a file,
 * confirm the name, upload. Baselines are append-only, so an upload here never
 * disturbs the ones already listed.
 */
export function BaselineUploadCard({
  sensorId,
  channelCount,
  canWrite,
  className,
}: BaselineUploadCardProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [setAsPrimary, setSetAsPrimary] = useState(false);
  const [savedBaseline, setSavedBaseline] = useState<Baseline | null>(null);

  const uploadMutation = useMutation({
    mutationFn: () =>
      uploadBaselineFile({
        sensorId,
        channelCount,
        name: name.trim() || defaultBaselineName(file!),
        description: description.trim() || null,
        setAsPrimary,
        file: file!,
      }),
    onSuccess: (baseline) => {
      setSavedBaseline(baseline);
      clearFile();
      setName("");
      setDescription("");
      setSetAsPrimary(false);
      queryClient.invalidateQueries({ queryKey: ["baseline-list", sensorId] });
      queryClient.invalidateQueries({ queryKey: ["primary-baseline", sensorId] });
    },
  });

  const clearFile = () => {
    setFile(null);
    // Resetting state alone leaves the native input holding the old filename,
    // so re-picking the same file fires no change event.
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    setSavedBaseline(null);
    setFile(selected);
    if (selected && !name.trim()) setName(defaultBaselineName(selected));
  };

  const handleRemove = () => {
    clearFile();
    setSavedBaseline(null);
    uploadMutation.reset();
  };

  const uploadError = uploadMutation.error as
    | { response?: { data?: { detail?: string } } }
    | null;

  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-border bg-warm/40 px-g4 py-g3 space-y-g3",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-sm font-bold text-foreground">Upload Baseline File</h4>
          <p className="mt-g1 text-sm text-muted-foreground">
            CSV or PDF captured during known-good operation. Parsed into {channelCount}{" "}
            channel{channelCount === 1 ? "" : "s"} and stored as a new baseline.
          </p>
        </div>
      </div>

      {!canWrite && (
        <p className="text-sm text-muted-foreground">
          Read-only users cannot upload baseline files.
        </p>
      )}

      {canWrite && (
        <>
          {!file ? (
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.pdf,text/csv,application/pdf"
              onChange={handleSelect}
              aria-label="Baseline file"
              className={cn(
                "w-full text-sm text-foreground file:mr-3 file:py-1.5 file:px-3",
                "file:rounded-md file:border file:border-border file:bg-white",
                "file:text-sm file:font-semibold file:text-foreground",
                "file:cursor-pointer hover:file:bg-warm"
              )}
            />
          ) : (
            <div
              className={cn(
                "flex items-center justify-between gap-g3 rounded-lg border border-border",
                "border-l-2 border-l-signal-light bg-white px-g4 py-g3"
              )}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-foreground">{file.name}</p>
                <p className="mt-g1 text-xs text-muted-foreground">
                  {formatFileSize(file.size)}
                  {file.type ? ` · ${file.type}` : ""}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={<Trash2 size={14} />}
                onClick={handleRemove}
                disabled={uploadMutation.isPending}
                className="shrink-0"
              >
                Remove
              </Button>
            </div>
          )}

          {file && (
            <div className="grid grid-cols-1 gap-g3 lg:grid-cols-2">
              <label className="flex flex-col gap-g1">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Baseline name
                </span>
                <input
                  type="text"
                  className={analysisInputClass}
                  value={name}
                  maxLength={200}
                  placeholder={defaultBaselineName(file)}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-g1">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Description (optional)
                </span>
                <input
                  type="text"
                  className={analysisInputClass}
                  value={description}
                  placeholder="e.g. Post-overhaul reference run"
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-g3">
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-border text-brand focus:ring-[rgba(245,166,35,0.15)]"
                checked={setAsPrimary}
                disabled={!file || uploadMutation.isPending}
                onChange={(e) => setSetAsPrimary(e.target.checked)}
              />
              Set as primary baseline
            </label>

            <Button
              type="button"
              size="sm"
              icon={
                uploadMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <FileUp size={14} />
                )
              }
              disabled={!file || uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {uploadMutation.isPending ? "Uploading…" : "Upload Baseline"}
            </Button>
          </div>

          {uploadMutation.isError && (
            <p className="text-sm font-semibold text-destructive">
              {uploadError?.response?.data?.detail ??
                "Baseline upload failed. Check the file format and try again."}
            </p>
          )}

          {savedBaseline && (
            <p className="inline-flex items-center gap-1.5 text-sm font-semibold text-machine-healthy">
              <CheckCircle2 size={14} />
              Saved “{savedBaseline.name}” ({savedBaseline.sample_count.toLocaleString()} samples,{" "}
              {savedBaseline.channel_count} channels).
            </p>
          )}
        </>
      )}
    </div>
  );
}
