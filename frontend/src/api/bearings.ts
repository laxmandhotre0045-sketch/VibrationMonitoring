import api from "./client";

/**
 * A catalogued bearing.
 *
 * The four frequencies are *orders of running speed*, not hertz — multiply by
 * the shaft speed in Hz to get the line to look for in a spectrum.
 */
export interface Bearing {
  /** The catalogue's own Bearing ID; what the equipment record stores. */
  source_bearing_id: number;
  manufacturer: string;
  designation: string;
  rolling_elements: number;
  ftf: number;
  bsf: number;
  bpfo: number;
  bpfi: number;
  /**
   * False when BPFO + BPFI does not equal the rolling-element count, which
   * means at least one of the catalogue's four values for this part is wrong.
   */
  is_consistent: boolean;
}

export interface BearingSearchResult {
  items: Bearing[];
  count: number;
  /** More rows matched than were returned — narrow the search. */
  truncated: boolean;
}

const BASE = "/api/v1/bearings";

/** One bearing by its catalogue ID, or null when there is no such row. */
export async function getBearing(sourceBearingId: number): Promise<Bearing | null> {
  try {
    const { data } = await api.get<Bearing>(`${BASE}/${sourceBearingId}`);
    return data;
  } catch (error) {
    // A typed-in ID that matches nothing is an ordinary outcome of this form,
    // not a failure worth surfacing as an error state.
    const status = (error as { response?: { status?: number } })?.response?.status;
    if (status === 404) return null;
    throw error;
  }
}

export async function searchBearings(params: {
  search?: string;
  manufacturer?: string;
  limit?: number;
}): Promise<BearingSearchResult> {
  const { data } = await api.get<BearingSearchResult>(BASE, {
    params: {
      search: params.search || undefined,
      manufacturer: params.manufacturer || undefined,
      limit: params.limit,
    },
  });
  return data;
}

export async function listBearingManufacturers(): Promise<string[]> {
  const { data } = await api.get<string[]>(`${BASE}/manufacturers`);
  return data;
}
