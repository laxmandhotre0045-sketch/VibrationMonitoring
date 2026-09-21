import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Loader2, Search, X } from "lucide-react";
import { getBearing, searchBearings, type Bearing } from "@/api/bearings";
import { FormField, TextInput } from "@/components/ui/FormField";
import { cn } from "@/lib/utils";

/** Long enough that a part number narrows the 89k-row catalogue usefully. */
const MIN_SEARCH_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 250;
const ID_DEBOUNCE_MS = 400;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** The four multipliers, as the catalogue lists them. */
function FrequencyReadout({ bearing }: { bearing: Bearing }) {
  const values: { label: string; value: number; hint: string }[] = [
    { label: "FTF", value: bearing.ftf, hint: "cage" },
    { label: "BSF", value: bearing.bsf, hint: "ball spin" },
    { label: "BPFO", value: bearing.bpfo, hint: "outer race" },
    { label: "BPFI", value: bearing.bpfi, hint: "inner race" },
  ];

  return (
    <div className="grid grid-cols-2 gap-g2 sm:grid-cols-4">
      {values.map((item) => (
        <div key={item.label} className="rounded-md border border-border bg-white px-g2 py-1.5">
          <p className="text-[10px] font-bold uppercase leading-none tracking-wide text-muted-foreground">
            {item.label}
          </p>
          <p className="mt-1 text-sm font-bold leading-tight text-foreground tabular-nums">
            {item.value.toFixed(3)}
          </p>
          <p className="text-[10px] leading-tight text-muted-foreground">{item.hint}</p>
        </div>
      ))}
    </div>
  );
}

interface BearingCatalogFieldProps {
  /** Which bearing position this is, e.g. "Drive End (DE)". */
  label: string;
  catalogId: number | null;
  onCatalogIdChange: (id: number | null) => void;
  bearingNumber: string;
  onBearingNumberChange: (value: string) => void;
  numberLabel: string;
  numberPlaceholder?: string;
  disabled?: boolean;
}

/**
 * One bearing position, resolved against the fault-frequency catalogue.
 *
 * Typing a Bearing ID fills in the manufacturer, part number, rolling-element
 * count and the four defect frequencies. Nobody memorises an 89k-row
 * catalogue's row numbers though, so the part number is searchable too and
 * picking a result writes the ID back — the ID field stays the thing that is
 * stored either way.
 *
 * The resolved values are shown but never saved onto the equipment record:
 * only the ID is. Copying them would duplicate reference data and go stale the
 * moment the catalogue is corrected.
 */
export function BearingCatalogField({
  label,
  catalogId,
  onCatalogIdChange,
  bearingNumber,
  onBearingNumberChange,
  numberLabel,
  numberPlaceholder,
  disabled = false,
}: BearingCatalogFieldProps) {
  const [idText, setIdText] = useState(catalogId != null ? String(catalogId) : "");
  const [searchText, setSearchText] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Keep the box in step when the form loads a record or the field is cleared
  // from outside, without fighting the user mid-type.
  useEffect(() => {
    setIdText((current) => {
      const incoming = catalogId != null ? String(catalogId) : "";
      return current === incoming || Number(current) === catalogId ? current : incoming;
    });
  }, [catalogId]);

  const debouncedId = useDebounced(idText.trim(), ID_DEBOUNCE_MS);
  const parsedId = /^\d+$/.test(debouncedId) ? Number(debouncedId) : null;

  const bearingQuery = useQuery({
    queryKey: ["bearing", parsedId],
    queryFn: () => getBearing(parsedId as number),
    enabled: parsedId !== null,
    staleTime: 5 * 60 * 1000,
  });

  const bearing = parsedId !== null ? bearingQuery.data ?? null : null;

  // Typing a valid ID is the commit: the form holds the ID, so it has to follow
  // the box rather than wait for a separate confirm step.
  useEffect(() => {
    if (parsedId === null) {
      if (debouncedId === "" && catalogId !== null) onCatalogIdChange(null);
      return;
    }
    if (bearingQuery.isSuccess && bearingQuery.data && catalogId !== parsedId) {
      onCatalogIdChange(parsedId);
    }
    // onCatalogIdChange is a form setter and stable enough for this to be safe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parsedId, debouncedId, bearingQuery.isSuccess, bearingQuery.data, catalogId]);

  const debouncedSearch = useDebounced(searchText.trim(), SEARCH_DEBOUNCE_MS);
  const searchQuery = useQuery({
    queryKey: ["bearing-search", debouncedSearch],
    queryFn: () => searchBearings({ search: debouncedSearch, limit: 20 }),
    enabled: debouncedSearch.length >= MIN_SEARCH_LENGTH,
    staleTime: 60 * 1000,
  });

  // Click-away, so the result list does not sit over the fields below it.
  useEffect(() => {
    if (!searchOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setSearchOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [searchOpen]);

  const select = (choice: Bearing) => {
    setIdText(String(choice.source_bearing_id));
    onCatalogIdChange(choice.source_bearing_id);
    // The free-text field is what a reader of the record sees first; keep it
    // agreeing with the catalogue entry it is now linked to.
    onBearingNumberChange(choice.designation);
    setSearchText("");
    setSearchOpen(false);
  };

  const clear = () => {
    setIdText("");
    onCatalogIdChange(null);
    setSearchText("");
    setSearchOpen(false);
  };

  const notFound =
    parsedId !== null && bearingQuery.isSuccess && bearingQuery.data === null;
  const results = searchQuery.data?.items ?? [];

  const status = useMemo(() => {
    if (parsedId !== null && bearingQuery.isLoading) return "loading" as const;
    if (notFound) return "missing" as const;
    if (bearing) return "resolved" as const;
    return "empty" as const;
  }, [parsedId, bearingQuery.isLoading, notFound, bearing]);

  return (
    <div ref={containerRef} className="rounded-lg border border-border bg-warm/40 p-g3">
      <p className="mb-g2 text-xs font-bold uppercase tracking-wide text-signal-dark">{label}</p>

      <div className="grid grid-cols-1 gap-g3 sm:grid-cols-2">
        <FormField label={numberLabel}>
          <TextInput
            value={bearingNumber}
            onChange={(e) => onBearingNumberChange(e.target.value)}
            placeholder={numberPlaceholder}
            disabled={disabled}
          />
        </FormField>

        <FormField label="Bearing ID (catalogue)">
          <div className="relative">
            <TextInput
              value={idText}
              onChange={(e) => setIdText(e.target.value.replace(/[^\d]/g, ""))}
              placeholder="e.g. 1"
              inputMode="numeric"
              disabled={disabled}
              error={status === "missing"}
            />
            {status === "loading" && (
              <Loader2
                size={15}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground"
              />
            )}
            {status === "resolved" && (
              <Check
                size={15}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-machine-healthy"
              />
            )}
          </div>
        </FormField>
      </div>

      <div className="relative mt-g3">
        <label className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Find by part number
        </label>
        <div className="relative mt-1">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={searchText}
            onChange={(e) => {
              setSearchText(e.target.value);
              setSearchOpen(true);
            }}
            onFocus={() => setSearchOpen(true)}
            placeholder="e.g. 6205-2RS or SKF 6205"
            disabled={disabled}
            className={cn(
              "w-full rounded-lg border border-border bg-white py-2.5 pl-9 pr-3 text-base",
              "focus:border-signal-light focus:outline-none focus:ring-2 focus:ring-[rgba(245,166,35,0.22)]",
              "disabled:cursor-not-allowed disabled:opacity-60"
            )}
          />
          {searchQuery.isFetching && (
            <Loader2
              size={15}
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground"
            />
          )}
        </div>

        {searchOpen && debouncedSearch.length >= MIN_SEARCH_LENGTH && (
          <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-white shadow-lg">
            {results.length === 0 ? (
              <p className="px-g3 py-g3 text-sm text-muted-foreground">
                {searchQuery.isFetching ? "Searching…" : "No catalogued bearing matches that."}
              </p>
            ) : (
              <>
                {results.map((item) => (
                  <button
                    key={item.source_bearing_id}
                    type="button"
                    onClick={() => select(item)}
                    className="flex w-full items-center justify-between gap-g3 border-b border-border/60 px-g3 py-2 text-left last:border-b-0 hover:bg-warm"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">
                        {item.manufacturer} {item.designation}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {item.rolling_elements} elements · BPFO {item.bpfo.toFixed(2)} · BPFI{" "}
                        {item.bpfi.toFixed(2)}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                      #{item.source_bearing_id}
                    </span>
                  </button>
                ))}
                {searchQuery.data?.truncated && (
                  <p className="px-g3 py-2 text-xs text-muted-foreground">
                    More matches exist — add the manufacturer or more of the part number.
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {status === "missing" && (
        <p className="mt-g2 text-sm font-medium text-destructive">
          No bearing with ID {parsedId} in the catalogue.
        </p>
      )}

      {bearing && (
        <div className="mt-g3 rounded-lg border border-border bg-white p-g3">
          <div className="mb-g2 flex flex-wrap items-center justify-between gap-g2">
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-foreground">
                {bearing.manufacturer} · {bearing.designation}
              </p>
              <p className="text-xs text-muted-foreground">
                {bearing.rolling_elements} rolling elements · catalogue ID{" "}
                {bearing.source_bearing_id}
              </p>
            </div>
            <button
              type="button"
              onClick={clear}
              disabled={disabled}
              className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-semibold text-muted-foreground hover:border-signal-light/55 hover:text-brand"
            >
              <X size={12} /> Unlink
            </button>
          </div>

          <FrequencyReadout bearing={bearing} />

          {!bearing.is_consistent && (
            <div className="mt-g2 flex items-start gap-g2 rounded-md border border-machine-warning/35 bg-machine-warning/10 px-g2 py-1.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-machine-warning" />
              <p className="text-xs leading-snug text-signal-deep">
                BPFO + BPFI should equal the rolling-element count for this bearing, and it does
                not. At least one catalogue value is wrong — check the datasheet before relying on
                these frequencies.
              </p>
            </div>
          )}

          <p className="mt-g2 text-xs leading-snug text-muted-foreground">
            Orders of running speed — multiply by shaft speed in Hz to get the frequency to look
            for in a spectrum.
          </p>
        </div>
      )}
    </div>
  );
}
