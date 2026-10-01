import api from "./client";
import type {
  FindingsResponse,
  HealthResponse,
  IsoResponse,
  PlotEvidence,
  SymptomsResponse,
} from "@/types/diagnosis";

/**
 * Phase 3: what the machine is thought to be doing, and how well it can be
 * seen at all.
 *
 * On this gateway `getFindings` returns an empty list on every machine, and
 * that is not a bug in any of these calls. A 0.278 s capture cannot separate
 * the bearing defect frequencies from ordinary shaft harmonics, so no rule
 * can fire. The response carries a `resolution` verdict explaining exactly
 * that, and every caller here is expected to show it rather than render the
 * empty list as good news.
 */

/** Open findings with their evidence and the plots that would prove them. */
export async function getFindings(
  sensorId: string,
): Promise<FindingsResponse> {
  const res = await api.get("/api/v1/diagnosis/findings", {
    params: { sensor_id: sensorId },
  });
  return res.data;
}

/** The health score with every contribution itemised (VIK-055). */
export async function getHealth(sensorId: string): Promise<HealthResponse> {
  const res = await api.get("/api/v1/diagnosis/health", {
    params: { sensor_id: sensorId },
  });
  return res.data;
}

/**
 * What the signal is doing, per channel (VIK-051).
 *
 * The most useful of the five on this gateway: symptoms are observations
 * rather than conclusions, so they survive a spectrum too coarse to name a
 * fault from.
 */
export async function getSymptoms(
  sensorId: string,
  uploadId?: string,
): Promise<SymptomsResponse> {
  const res = await api.get("/api/v1/diagnosis/symptoms", {
    params: { sensor_id: sensorId, upload_id: uploadId },
  });
  return res.data;
}

/** The ISO 10816-3 zone, or every zone it could be (VIK-056). */
export async function getIso(
  sensorId: string,
  channel = 0,
): Promise<IsoResponse> {
  const res = await api.get("/api/v1/diagnosis/iso", {
    params: { sensor_id: sensorId, channel },
  });
  return res.data;
}

/** Which plots prove a given fault, best first (VIK-059). */
export async function getPlotEvidence(
  faultKey: string,
): Promise<PlotEvidence[]> {
  const res = await api.get("/api/v1/diagnosis/plot-evidence", {
    params: { fault_key: faultKey },
  });
  return res.data.plots ?? [];
}
