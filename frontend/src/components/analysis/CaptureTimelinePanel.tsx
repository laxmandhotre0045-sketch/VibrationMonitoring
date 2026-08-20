import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, subDays } from "date-fns";
import type { SensorDataUpload } from "@/types/measurements";
import { listUploads } from "@/api/measurements";
import { CompactDateRangeBar } from "./CompactDateRangeBar";
import { CaptureTimeline, type DayFilter } from "./CaptureTimeline";

interface CaptureTimelinePanelProps {
  sensorId: string;
  selectedUploadId: string;
  onSelectUpload: (uploadId: string, upload?: SensorDataUpload) => void;
  disabled?: boolean;
  refreshKey?: number;
}

function defaultRange() {
  const to = format(new Date(), "yyyy-MM-dd");
  const from = format(subDays(new Date(), 30), "yyyy-MM-dd");
  return { from, to };
}

export function CaptureTimelinePanel({
  sensorId,
  selectedUploadId,
  onSelectUpload,
  disabled = false,
  refreshKey = 0,
}: CaptureTimelinePanelProps) {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selectedDay, setSelectedDay] = useState<DayFilter>("all");

  useEffect(() => {
    if (!sensorId) {
      setFromDate("");
      setToDate("");
      setSelectedDay("all");
      return;
    }
    const { from, to } = defaultRange();
    setFromDate(from);
    setToDate(to);
    setSelectedDay("all");
  }, [sensorId]);

  const rangeValid = !!fromDate && !!toDate && fromDate <= toDate;

  const { data: uploadList, isPending, isFetching } = useQuery({
    queryKey: ["sensor-uploads-timeline", sensorId, fromDate, toDate, refreshKey],
    queryFn: () => listUploads(sensorId, { fromDate, toDate }),
    enabled: !!sensorId && rangeValid,
  });

  const isResolving = isPending || isFetching;
  const files = isResolving ? [] : (uploadList?.items ?? []);
  const totalFiles =
    !isResolving && uploadList != null ? uploadList.total : null;

  const handleSelectFile = (fileId: string) => {
    const upload = files.find((f) => f.id === fileId);
    onSelectUpload(fileId, upload);
  };

  if (!sensorId) {
    return (
      <p className="text-sm text-muted-foreground text-center py-g3">
        Select a sensor above to browse capture history.
      </p>
    );
  }

  return (
    <div className="space-y-g2">
      <CompactDateRangeBar
        fromDate={fromDate}
        toDate={toDate}
        onFromChange={(value) => {
          setFromDate(value);
          setSelectedDay("all");
        }}
        onToChange={(value) => {
          setToDate(value);
          setSelectedDay("all");
        }}
        disabled={disabled}
      />

      {rangeValid && (
        <CaptureTimeline
          files={files}
          totalFiles={totalFiles}
          fromDate={fromDate}
          toDate={toDate}
          selectedFileId={selectedUploadId || null}
          selectedDay={selectedDay}
          onSelectDay={setSelectedDay}
          onSelectFile={handleSelectFile}
          isLoading={isResolving}
        />
      )}
    </div>
  );
}
