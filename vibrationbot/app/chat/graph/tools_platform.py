"""Measurement-platform tools exposed to the chat agent.

Thin wrappers over ``sql_agent`` — the backend library owns all the logic, and
this file only adapts its ``AgentResult`` into the LangChain tool contract. Any
fix to resolution or flattening belongs in ``sql_agent``, not here, so the
chatbot and any future agent stay in step.

Like tools_domain.py these use ``response_format="content_and_artifact"``: the
model reads a short summary while the real payload travels as an artifact it
never sees and therefore cannot paraphrase into something untrue. The model may
say "240 rows across 8 channels" because that came from counting the rows; it is
never handed the full data, so it cannot invent a reading that is not in it.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from vibcore.records import ComputationRecord
from sql_agent import SensorDataAgent
from sql_agent.config import PLATFORM_MAX_UPLOADS

logger = logging.getLogger(__name__)


class ListSensorsArgs(BaseModel):
    filter_text: str = Field(
        default="",
        description=(
            "Optional words to narrow the list, e.g. a plant, machine or "
            "mounting location. Leave empty to list every sensor."
        ),
    )


class ExportSensorArgs(BaseModel):
    sensor: str = Field(
        ...,
        description=(
            "Which sensor to read. A sensor UUID, a device id, or descriptive "
            "text such as 'cooling water pump horizontal'."
        ),
    )
    from_date: str | None = Field(
        default=None, description="Optional start date, YYYY-MM-DD (UTC)."
    )
    to_date: str | None = Field(
        default=None, description="Optional end date, YYYY-MM-DD (UTC)."
    )
    max_captures: int = Field(
        default=PLATFORM_MAX_UPLOADS,
        ge=1,
        le=2000,
        description="Cap on how many captures to include, newest first.",
    )


def build_platform_tools(agent: SensorDataAgent | None = None) -> list[StructuredTool]:
    agent = agent or SensorDataAgent()

    def list_platform_sensors(filter_text: str = "") -> tuple[str, dict[str, Any] | None]:
        """List sensors registered on the measurement platform."""
        result = agent.list_sensors(filter_text)
        if not result.ok:
            return result.error or "The measurement platform is unavailable.", None
        if not result.data:
            return (
                "No sensors match that description."
                if filter_text
                else "The platform has no sensors registered yet."
            ), None

        lines = [
            f"- {e['machine_name']} / {e['mounting_location']} ({e['orientation']}) "
            f"- {e['plant_name']}/{e['area']}/{e['line']} - id {e['sensor_id']}"
            for e in result.data[:25]
        ]
        more = f"\n... and {len(result.data) - 25} more" if len(result.data) > 25 else ""

        record = ComputationRecord(
            tool="list_platform_sensors",
            inputs={"filter_text": filter_text},
            outputs={"count": len(result.data), "sensors": result.data[:100]},
            formula="Equipment list joined to each machine's sensor configurations",
            assumptions=["Read from the platform API as a read-only user."],
            confidence=1.0,
        )
        return (
            f"{len(result.data)} sensor(s):\n" + "\n".join(lines) + more,
            record.as_dict(),
        )

    def export_sensor_data(
        sensor: str,
        from_date: str | None = None,
        to_date: str | None = None,
        max_captures: int = PLATFORM_MAX_UPLOADS,
    ) -> tuple[str, dict[str, Any] | None]:
        """Read one sensor's measurement history and save it as a CSV file."""
        result = agent.get_sensor_data(
            sensor,
            from_date=from_date,
            to_date=to_date,
            max_captures=max_captures,
            include_csv=True,
            write_csv=True,
        )
        if not result.ok:
            # An ambiguous or unknown sensor names the alternatives in the error,
            # so hand it back verbatim for the model to relay as a question.
            return result.error or "Could not read the measurement platform.", None

        m = result.meta
        if m["csv_rows"] == 0:
            return (
                f"{m['sensor']} is registered but has no captures yet, so there is "
                "nothing to export.",
                None,
            )

        truncated = (
            f" (newest {m['captures_exported']} of {m['captures_available']})"
            if m["truncated"]
            else ""
        )
        summary_text = (
            f"Read {m['sensor']}.\n"
            f"- {m['csv_rows']} rows from {m['captures_exported']} capture(s){truncated}\n"
            f"- channels {m['channels']}, features {len(m['feature_codes'])}\n"
            f"- window {m['first_observed_at']} to {m['last_observed_at']}\n"
            f"- status counts {m['status_counts']}\n"
            f"- saved to {m.get('csv_path', '(not written)')}\n\n"
            f"Preview:\n{m.get('csv_preview', '')}"
        )

        # The CSV text itself is dropped from the artifact - it is already on
        # disk, and a 90 KB string in the graph state would be carried through
        # every later node for no benefit.
        outputs = {k: v for k, v in m.items() if k != "csv"}
        record = ComputationRecord(
            tool="export_sensor_data",
            inputs={
                "sensor": sensor,
                "from_date": from_date,
                "to_date": to_date,
                "max_captures": max_captures,
            },
            outputs=outputs,
            formula=(
                "Captures joined to their per-channel features and flattened to one "
                "row per (capture x channel x feature)"
            ),
            assumptions=m.get("caveats", []),
            confidence=1.0,
        )
        return summary_text, record.as_dict()

    specs = [
        (list_platform_sensors, "list_platform_sensors", ListSensorsArgs),
        (export_sensor_data, "export_sensor_data", ExportSensorArgs),
    ]
    return [
        StructuredTool.from_function(
            func=func, name=name, args_schema=schema, response_format="content_and_artifact"
        )
        for func, name, schema in specs
    ]
