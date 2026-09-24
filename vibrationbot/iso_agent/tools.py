"""The ISO severity tool: limits come from tested code, never from a page.

This exists because reading a limit out of the ingested standard was measured
and found unsafe, in two separate ways.

**The PDF cannot answer the question.** The ingested copy of ISO 10816-3
carries Annex A Tables A.1 and A.2 -- Groups 1 and 2 -- and nothing else. The
standard also defines Group 3 (pumps with a separate driver) and Group 4
(pumps with an integrated driver), and pumps belong to those groups *whatever
their rated power*. A question about a 55 kW pump therefore has no answer
anywhere in the document, and an agent reading it will confidently return the
Group 2 row instead.

**The judgement is arithmetic, not language.** Choosing a group from a power
rating and a machine type, then a row from a support class, then the velocity
column rather than the displacement one, is four lookups. Measured over five
runs the model got the whole chain right once. ``app/domain/iso10816.py`` gets
it right every time, is unit-tested against the published values, and already
carries all four groups.

So the numbers come from there. The document is still cited -- for what a zone
*means* and what action it implies, which is prose the standard states and the
tool does not. That split is what ``vibcore/data/iso10816_3.json`` asks for
in its own header: "The ingested standard PDF supplies the prose ... the
numbers come from here."

Ambiguity is reported, never resolved by guessing. "A 55 kW pump" does not say
whether the driver is integrated, and the two answers differ by 60%, so both
are returned with the question that separates them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from vibcore import iso10816

logger = logging.getLogger(__name__)

#: Boundary order in the reference table.
_BOUNDARIES = ("A/B", "B/C", "C/D")


class ZoneLimitsArgs(BaseModel):
    machine_type: str = Field(
        ...,
        description=(
            "What the machine is, in the asker's own words: 'centrifugal pump', "
            "'motor', 'fan', 'compressor'. Pumps are classified separately from "
            "everything else, so this matters as much as the power rating."
        ),
    )
    power_kw: float | None = Field(
        None, gt=0, description="Rated power in kW, if the question gives one."
    )
    foundation: str | None = Field(
        None,
        description="'rigid' or 'flexible'. Omit if the question does not say; both are returned.",
    )
    integrated_driver: bool | None = Field(
        None,
        description=(
            "For a pump only: True if the driver is integrated, False if separate. "
            "Omit when the question does not say -- both groups are then returned."
        ),
    )


def _table(group: int, foundation: str) -> dict[str, float]:
    data = json.loads(iso10816.DATA_PATH.read_text(encoding="utf-8"))
    values = data["velocity_rms_mm_s"][str(group)][foundation]
    return dict(zip(_BOUNDARIES, values))


def _describe(group: int, foundation: str) -> dict[str, Any]:
    data = json.loads(iso10816.DATA_PATH.read_text(encoding="utf-8"))
    info = data["groups"][str(group)]
    return {
        "group": group,
        "group_name": info["name"],
        "group_scope": info["description"],
        "support": foundation,
        "boundaries_mm_s_rms": _table(group, foundation),
        "units": "mm/s RMS, broadband 10-1000 Hz, measured on non-rotating parts",
    }


def iso_zone_limits(
    machine_type: str,
    power_kw: float | None = None,
    foundation: str | None = None,
    integrated_driver: bool | None = None,
) -> str:
    """ISO 10816-3 zone boundaries for a machine, from the unit-tested tables.

    ALWAYS use this for a numeric vibration limit or zone boundary. Never read
    one out of a document excerpt: the ingested standard contains only the
    Group 1 and Group 2 tables, so a pump has no correct answer in it.
    """
    kind = (machine_type or "").strip().lower()
    supports = [foundation.lower()] if foundation else ["rigid", "flexible"]
    supports = [s for s in supports if s in ("rigid", "flexible")] or ["rigid", "flexible"]

    # A pump is Group 3 or 4 by construction; which one depends on the driver.
    if "pump" in kind and integrated_driver is None:
        candidates = [3, 4]
        ambiguity = (
            "This is a pump, so ISO 10816-3 classifies it as Group 3 (separate "
            "driver) or Group 4 (integrated driver) regardless of rated power. "
            "The question does not say which, and the two differ substantially. "
            "Report BOTH and ask the engineer which driver arrangement applies."
        )
    else:
        group = iso10816.infer_machine_group(
            power_kw=power_kw,
            machine_type=machine_type,
            integrated_driver=bool(integrated_driver),
        )
        if group is None:
            return json.dumps(
                {
                    "error": (
                        "Cannot determine the ISO group. Supply the rated power in kW "
                        "and the machine type. Below 15 kW, Groups 1-4 do not apply."
                    )
                }
            )
        candidates = [group]
        ambiguity = None

    results = [_describe(g, s) for g in candidates for s in supports]
    payload: dict[str, Any] = {
        "standard": "ISO 10816-3 (velocity zone limits; ISO 20816-3 is identical)",
        "source": "vibcore/data/iso10816_3.json - hardcoded, unit-tested, not retrieved",
        "boundary_convention": iso10816.BOUNDARY_CONVENTION,
        "results": results,
    }
    if ambiguity:
        payload["ambiguous"] = ambiguity
    payload["note"] = (
        "These figures are authoritative and must be quoted exactly as given. Do "
        "not take a limit from any document excerpt, and do not convert between "
        "the velocity (mm/s) and displacement (micrometre) columns."
    )
    return json.dumps(payload)


def build_iso_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=iso_zone_limits, name="iso_zone_limits", args_schema=ZoneLimitsArgs
        )
    ]
