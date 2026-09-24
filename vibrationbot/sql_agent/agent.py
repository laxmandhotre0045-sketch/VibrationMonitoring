"""The backend-facing entry point: sensor data, shaped for another agent to consume.

This is a library, not a service. It has no HTTP routes and no UI. A downstream
agent — a diagnosis engine, a report writer, a trend forecaster — calls one of
these methods and gets a predictable envelope back.

Two decisions shape the return type, and both exist because the consumer is a
machine rather than a person:

**Failures are values, not exceptions.** ``ok`` is False and ``error`` carries a
sentence a calling agent can act on or relay. An agent mid-plan should not have
to wrap every call in try/except to avoid dying on "that sensor name matched
three sensors".

**Caveats travel with the data.** ``meta["caveats"]`` states, every time, that
values are in scaled engineering units and that ``no_baseline`` means "not
assessed" rather than "healthy". A downstream model that never sees the schema
docs would otherwise compare RMS across machines, or count ``no_baseline`` as
passing — both are wrong, and both look reasonable in a summary.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sql_agent.client import PlatformClient, PlatformError, platform_client
from sql_agent.config import (
    EXPORTS_DIR,
    PLATFORM_CSV_PREVIEW_ROWS,
    PLATFORM_MAX_UPLOADS,
)
from sql_agent.dataset import (
    CSV_COLUMNS,
    build_sensor_index,
    collect_sensor_dataset,
    dataset_to_rows,
    export_filename,
    resolve_sensor,
    rows_to_csv,
    summarize,
)

logger = logging.getLogger(__name__)

#: Restated on every result so a consumer that never read this module still gets
#: them. Cheap to carry, expensive to omit.
CAVEATS = [
    "Values are the platform's stored feature values in scaled engineering units "
    "(unit='scaled_eng'), not converted to g, mm/s or micrometres. Comparing raw "
    "magnitudes across different machines is not meaningful; use crest_factor, "
    "status, or a ratio against the sensor's own baseline instead.",
    "status='no_baseline' means the feature was not assessed because no healthy "
    "reference exists for this sensor. It does not mean the machine is healthy.",
    "Rows are ordered by observed_at, which is the device's capture clock where "
    "one was supplied and server receipt otherwise. Only observed_at orders a "
    "trend correctly.",
    "Shaft speed behind amplitude_1x/2x/3x is estimated from the spectrum unless "
    "the capture carries rotation_speed_rpm. Treat harmonic amplitudes as "
    "provisional when rotation_speed_rpm is empty.",
]


@dataclass
class AgentResult:
    """What every entry point returns. Stable shape, success or failure."""

    ok: bool
    kind: str
    data: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "data": self.data,
            "meta": self.meta,
            "error": self.error,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def summary_text(self) -> str:
        """A few lines suitable for putting straight into a model's context."""
        if not self.ok:
            return f"[{self.kind}] failed: {self.error}"
        m = self.meta
        if self.kind == "sensor_list":
            return f"[{self.kind}] {m.get('count', len(self.data))} sensor(s)."
        return (
            f"[{self.kind}] {m.get('sensor')} — {m.get('csv_rows')} rows from "
            f"{m.get('captures_exported')} of {m.get('captures_available')} capture(s); "
            f"channels {m.get('channels')}; statuses {m.get('status_counts')}; "
            f"window {m.get('first_observed_at')} to {m.get('last_observed_at')}."
        )


def _fail(kind: str, message: str) -> AgentResult:
    return AgentResult(
        ok=False,
        kind=kind,
        error=message,
        meta={"generated_at": datetime.now(timezone.utc).isoformat()},
    )


def _preview(csv_text: str, limit: int) -> str:
    lines = csv_text.splitlines()
    if len(lines) <= limit + 1:
        return csv_text.strip()
    remaining = len(lines) - 1 - limit
    return "\n".join(lines[: limit + 1]) + f"\n... {remaining} more rows"


class SensorDataAgent:
    """Read a sensor's history and hand it to whoever asked, in a fixed shape.

    Read-only by construction: the client underneath implements GET and a login
    POST, and authenticates as a platform account holding the read-only ``user``
    role. There is no method here, and no credential behind it, that could
    modify anything.
    """

    def __init__(self, client: PlatformClient | None = None) -> None:
        self.client = client or platform_client

    # ------------------------------------------------------------ inventory --

    def list_sensors(self, filter_text: str = "") -> AgentResult:
        """Every sensor, or those matching every word in ``filter_text``."""
        try:
            index = build_sensor_index(self.client)
        except PlatformError as exc:
            return _fail("sensor_list", f"Measurement platform unavailable: {exc}")

        terms = [t for t in (filter_text or "").lower().split() if t]
        if terms:
            index = [
                e
                for e in index
                if all(
                    t in " ".join(str(v or "") for v in e.values()).lower()
                    for t in terms
                )
            ]

        return AgentResult(
            ok=True,
            kind="sensor_list",
            data=index,
            meta={
                "count": len(index),
                "filter_text": filter_text,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def resolve(self, sensor: str) -> AgentResult:
        """Turn a name, device id or UUID into exactly one sensor.

        Ambiguity is an error rather than a guess — an analysis silently run on
        the wrong bearing is worse than a question back to the caller.
        """
        try:
            entry = resolve_sensor(self.client, sensor)
        except LookupError as exc:
            return _fail("sensor_resolve", str(exc))
        except PlatformError as exc:
            return _fail("sensor_resolve", f"Measurement platform unavailable: {exc}")
        return AgentResult(
            ok=True,
            kind="sensor_resolve",
            data=[entry],
            meta={"generated_at": datetime.now(timezone.utc).isoformat()},
        )

    # ----------------------------------------------------------------- data --

    def get_sensor_data(
        self,
        sensor: str,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        max_captures: int = PLATFORM_MAX_UPLOADS,
        include_csv: bool = True,
        write_csv: bool = False,
    ) -> AgentResult:
        """One sensor's full measurement history, structured by sensor id.

        ``data`` is one row per (capture x channel x feature). ``meta`` carries
        the counts, the column order, the caveats, and — when asked for — the
        CSV text and a preview of it.
        """
        try:
            entry = resolve_sensor(self.client, sensor)
            dataset = collect_sensor_dataset(
                self.client,
                entry,
                max_uploads=max_captures,
                from_date=from_date,
                to_date=to_date,
            )
        except LookupError as exc:
            return _fail("sensor_data", str(exc))
        except PlatformError as exc:
            return _fail("sensor_data", f"Measurement platform unavailable: {exc}")

        rows = dataset_to_rows(dataset)
        meta: dict[str, Any] = {
            **summarize(dataset, rows),
            "columns": CSV_COLUMNS,
            "caveats": CAVEATS,
            "query": {
                "sensor": sensor,
                "from_date": from_date,
                "to_date": to_date,
                "max_captures": max_captures,
            },
        }

        if include_csv or write_csv:
            csv_text = rows_to_csv(rows)
            if include_csv:
                meta["csv"] = csv_text
                meta["csv_preview"] = _preview(csv_text, PLATFORM_CSV_PREVIEW_ROWS)
            if write_csv:
                EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
                filename = export_filename(dataset)
                target = EXPORTS_DIR / filename
                # newline="" so the csv module's \r\n survives rather than
                # becoming \r\r\n on Windows.
                with open(target, "w", encoding="utf-8", newline="") as fh:
                    fh.write(csv_text)
                meta["csv_path"] = str(target)
                meta["csv_filename"] = filename
                logger.info("Wrote %s (%d rows)", target, len(rows))

        return AgentResult(ok=True, kind="sensor_data", data=rows, meta=meta)

    def get_latest_reading(self, sensor: str) -> AgentResult:
        """Only the most recent capture — the cheap call for a health check.

        A diagnosis agent asking "how is this machine right now" does not need
        a year of history, and pulling one capture instead of two hundred is the
        difference between one features request and two hundred.
        """
        result = self.get_sensor_data(sensor, max_captures=1, include_csv=False)
        if result.ok:
            result.kind = "sensor_latest"
        return result


#: Module-level instance for callers that just want the default configuration.
sensor_agent = SensorDataAgent()
