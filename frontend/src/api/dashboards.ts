import api from "./client";
import type {
  FleetResponse,
  OperatorResponse,
  ReliabilityResponse,
} from "@/types/dashboards";

/**
 * Section 19's dashboards and section 12.2's reliability score.
 *
 * Nothing here substitutes a default. The fleet averages are computed over
 * the machines that could be scored and the response names the ones that
 * could not; passing that through unchanged is the whole point, because an
 * average over half a plant that does not say so is worse than none.
 */

/** Section 19.1 — is it running, and is it alright. */
export async function getOperatorView(
  plantName?: string,
): Promise<OperatorResponse> {
  const res = await api.get("/api/v1/diagnosis/operator", {
    params: { plant_name: plantName },
  });
  return res.data;
}

/** Section 19.3 — the whole site in one picture. */
export async function getFleet(plantName?: string): Promise<FleetResponse> {
  const res = await api.get("/api/v1/diagnosis/fleet", {
    params: { plant_name: plantName },
  });
  return res.data;
}

/** Section 12.2 — how dependable one machine's record is. */
export async function getReliability(
  sensorId: string,
): Promise<ReliabilityResponse> {
  const res = await api.get("/api/v1/diagnosis/reliability", {
    params: { sensor_id: sensorId },
  });
  return res.data;
}
