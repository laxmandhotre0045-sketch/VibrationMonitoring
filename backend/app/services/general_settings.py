"""Section 4.1's general AI settings, and honouring them.

Three switches and two filter bands. The switches matter more than they
look: every engine currently runs unconditionally, so a machine being
commissioned or running a test regime produces findings that are true of a
machine nobody is trying to diagnose, and they reach the same baselines and
the same queue as everything else.

**A setting is only real if something reads it.** The other half of this
module is the readers -- `mode_detection_enabled` is checked before the
mode is detected, `fault_detection_enabled` before findings are ranked.
A settings table nothing consults is a form.

**Turning something off is recorded, not just applied.** The row carries
who did it and why, and the database refuses a disabled switch with no
note. A switch found six months later by somebody who cannot tell whether
it was deliberate is worse than no switch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TABLE = "ai_general_settings"


@dataclass
class GeneralSettings:
    """What is switched on for one machine, and how it is filtered."""
    mode_detection_enabled: bool = True
    fault_detection_enabled: bool = True
    auto_reports_enabled: bool = True
    highpass_hz: Optional[float] = None
    lowpass_hz: Optional[float] = None
    envelope_band_low_hz: Optional[float] = None
    envelope_band_high_hz: Optional[float] = None
    #: Where these came from: the machine's own row, the plant default, or
    #: the built-in fallback. Worth reporting, because "everything is on"
    #: means something different when nobody has ever configured anything.
    source: str = "default"
    notes: Optional[str] = None

    @property
    def anything_disabled(self) -> bool:
        return not (self.mode_detection_enabled
                    and self.fault_detection_enabled
                    and self.auto_reports_enabled)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode_detection_enabled": self.mode_detection_enabled,
            "fault_detection_enabled": self.fault_detection_enabled,
            "auto_reports_enabled": self.auto_reports_enabled,
            "highpass_hz": self.highpass_hz,
            "lowpass_hz": self.lowpass_hz,
            "envelope_band_low_hz": self.envelope_band_low_hz,
            "envelope_band_high_hz": self.envelope_band_high_hz,
            "anything_disabled": self.anything_disabled,
            "source": self.source, "notes": self.notes,
        }


def _row_to_settings(row: Any, source: str) -> GeneralSettings:
    return GeneralSettings(
        mode_detection_enabled=bool(row["mode_detection_enabled"]),
        fault_detection_enabled=bool(row["fault_detection_enabled"]),
        auto_reports_enabled=bool(row["auto_reports_enabled"]),
        highpass_hz=row["highpass_hz"],
        lowpass_hz=row["lowpass_hz"],
        envelope_band_low_hz=row["envelope_band_low_hz"],
        envelope_band_high_hz=row["envelope_band_high_hz"],
        source=source, notes=row["notes"])


def settings_for(db: Session,
                 equipment_id: Optional[UUID] = None) -> GeneralSettings:
    """This machine's settings, falling back to the plant default.

    Never raises. These are read on every capture, and a bad settings row
    must not stop a machine being monitored -- but it must not silently
    turn an engine *off* either, so the fallback is everything enabled.
    """
    try:
        if equipment_id is not None:
            row = db.execute(text(f"""
                SELECT * FROM {TABLE} WHERE equipment_id = :e
            """), {"e": str(equipment_id)}).mappings().fetchone()
            if row is not None:
                return _row_to_settings(row, "machine")

        row = db.execute(text(f"""
            SELECT * FROM {TABLE} WHERE equipment_id IS NULL
        """)).mappings().fetchone()
        if row is not None:
            return _row_to_settings(row, "plant")
    except Exception:
        logger.exception("Could not read general settings for %s",
                         equipment_id)

    return GeneralSettings(source="fallback")


def update(db: Session, *, equipment_id: Optional[UUID], analyst: str,
           notes: Optional[str] = None, **changes: Any) -> GeneralSettings:
    """Change a setting, recording who and why.

    Disabling an engine without a reason is refused here as well as in the
    database, so the caller gets a sentence rather than an integrity error.
    """
    allowed = {"mode_detection_enabled", "fault_detection_enabled",
               "auto_reports_enabled", "highpass_hz", "lowpass_hz",
               "envelope_band_low_hz", "envelope_band_high_hz"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"not a general setting: {sorted(unknown)}")

    disabling = any(changes.get(k) is False for k in
                    ("mode_detection_enabled", "fault_detection_enabled",
                     "auto_reports_enabled"))
    if disabling and not (notes or "").strip():
        raise ValueError(
            "Turning an engine off needs a reason. A switch found six "
            "months later by somebody who cannot tell whether it was "
            "deliberate is worse than no switch at all.")

    current = settings_for(db, equipment_id)
    merged = {**{k: getattr(current, k) for k in allowed}, **changes}

    columns = ", ".join(allowed)
    placeholders = ", ".join(f":{k}" for k in allowed)
    updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in allowed)

    params = {**merged, "notes": notes, "analyst": analyst,
              "equipment_id": str(equipment_id) if equipment_id else None}

    if equipment_id is None:
        # The plant-wide row is targeted by an explicit UPDATE rather than
        # ON CONFLICT. Postgres treats NULLs as distinct in a unique index,
        # so `ON CONFLICT (equipment_id)` never matches the NULL row --
        # every edit to the plant default inserted another one instead of
        # updating it, silently, and `settings_for` then returned whichever
        # duplicate the planner reached first.
        assignments = ", ".join(f"{k} = :{k}" for k in allowed)
        updated = db.execute(text(f"""
            UPDATE {TABLE}
               SET {assignments}, notes = :notes, updated_by = :analyst,
                   updated_at = now()
             WHERE equipment_id IS NULL
        """), params).rowcount
        if not updated:
            db.execute(text(f"""
                INSERT INTO {TABLE} (equipment_id, {columns}, notes,
                                     updated_by, updated_at)
                VALUES (NULL, {placeholders}, :notes, :analyst, now())
            """), params)
    else:
        db.execute(text(f"""
            INSERT INTO {TABLE} (equipment_id, {columns}, notes, updated_by,
                                 updated_at)
            VALUES (:equipment_id, {placeholders}, :notes, :analyst, now())
            ON CONFLICT (equipment_id) DO UPDATE SET
                {updates},
                notes = EXCLUDED.notes,
                updated_by = EXCLUDED.updated_by,
                updated_at = EXCLUDED.updated_at
        """), params)

    return settings_for(db, equipment_id)
