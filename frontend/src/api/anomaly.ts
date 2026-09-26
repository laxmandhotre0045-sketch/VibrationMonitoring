import api from "./client";
import type {
  AlarmSummary,
  CaptureMode,
  CaptureScores,
  DetectorScore,
  OperatingMode,
  ScoredCapture,
  Sensitivity,
  SensitivityProfile,
} from "@/types/anomaly";

/**
 * The Phase 2 endpoints: how unusual each reading was, and what is ringing.
 *
 * Nothing here converts a null into a number or a missing thing into an
 * empty success. Where the backend says "could not be scored" this hands
 * that through unchanged, because the screens above are built to show it —
 * a reading nothing has been compared to is not a reading that looks
 * ordinary, and smoothing that over here would undo the whole engine.
 */

/** The captures on a machine that have been scored, newest first. */
export async function listScoredCaptures(
  sensorId: string,
  limit = 100,
): Promise<ScoredCapture[]> {
  const res = await api.get("/api/v1/anomaly/captures", {
    params: { sensor_id: sensorId, limit },
  });
  return res.data;
}

export async function getCaptureScores(
  uploadId: string,
  options?: { channel?: number; scoredOnly?: boolean },
): Promise<CaptureScores> {
  const res = await api.get("/api/v1/anomaly/scores", {
    params: {
      upload_id: uploadId,
      channel: options?.channel,
      scored_only: options?.scoredOnly,
    },
  });
  return res.data;
}

export async function getDetectorScores(uploadId: string): Promise<DetectorScore[]> {
  const res = await api.get("/api/v1/anomaly/detectors", {
    params: { upload_id: uploadId },
  });
  return res.data;
}

export async function getAlarms(sensorId: string): Promise<AlarmSummary> {
  const res = await api.get("/api/v1/anomaly/alarms", {
    params: { sensor_id: sensorId },
  });
  return res.data;
}

/**
 * Mark one ringing alarm as seen.
 *
 * This does not silence it. The machine has not got better; what changes is
 * that somebody has looked — so the response still carries the alarm, and
 * the screen still shows it.
 */
export async function acknowledgeAlarm(payload: {
  sensorId: string;
  channel: number;
  featureCode: string;
  note?: string;
}): Promise<AlarmSummary> {
  const res = await api.post("/api/v1/anomaly/alarms/acknowledge", {
    sensor_id: payload.sensorId,
    channel: payload.channel,
    feature_code: payload.featureCode,
    note: payload.note,
  });
  return res.data;
}

export async function getSensitivity(equipmentId: string): Promise<Sensitivity> {
  const res = await api.get("/api/v1/anomaly/sensitivity", {
    params: { equipment_id: equipmentId },
  });
  return res.data;
}

export async function setSensitivity(
  equipmentId: string,
  profile: SensitivityProfile,
  overrides?: Record<string, number>,
): Promise<Sensitivity> {
  const res = await api.put(
    "/api/v1/anomaly/sensitivity",
    { profile, overrides },
    { params: { equipment_id: equipmentId } },
  );
  return res.data;
}

export async function listOperatingModes(
  equipmentId: string,
): Promise<OperatingMode[]> {
  const res = await api.get("/api/v1/operating-modes", {
    params: { equipment_id: equipmentId },
  });
  return res.data;
}

/**
 * The mode one capture was taken in.
 *
 * A capture nothing has ever classified is a 404, and that is handed back as
 * `null` rather than as an unknown verdict — "we looked and could not tell"
 * and "nothing has ever looked at this" are different facts, and only the
 * first is the engine declining to guess.
 */
export async function getCaptureMode(uploadId: string): Promise<CaptureMode | null> {
  try {
    const res = await api.get("/api/v1/operating-modes/capture", {
      params: { upload_id: uploadId },
    });
    return res.data;
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 404) return null;
    throw err;
  }
}
