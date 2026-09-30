"""Record which mode each capture was taken in — VIK-039 storage.

The detector decides; this stores the decision next to the capture, the way
the quality verdict is stored next to it. Same reason: a finding recorded
three months ago was judged against one mode's normal, and the bands will be
retuned. When they are, the old finding must still show the mode that was
actually chosen and the evidence it was chosen from, or it becomes
unexplainable.

One row per capture, replaced rather than appended on a re-run, because
re-running the detector is a corrected opinion and not a second one.

Never raises. A capture whose mode could not be decided is still a capture
worth keeping, and it already has an honest representation -- unknown.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.versions import version_of
from app.ai.operating_mode import UNKNOWN, ModeVerdict, detect_mode
from app.services.operating_mode_setup import load_bands

logger = logging.getLogger(__name__)

TABLE = "capture_operating_modes"
# Declared in `app.ai.versions`, not here. Five modules each
# holding their own constant is five places to forget, and
# section 22 turns on no version changing silently.
ENGINE_VERSION = version_of("operating_mode")


def overall_level(channels: dict[str, list[float]]) -> Optional[float]:
    """One vibration level for the capture, in g.

    The median channel rather than the mean of all of them: one dead or
    clipped channel should not decide whether the machine is running, and on
    this gateway the channels differ by six times between quietest and
    loudest even when every one of them is healthy.
    """
    levels = []
    for samples in channels.values():
        array = np.asarray(samples, dtype=float)
        if array.size:
            centred = array - float(np.mean(array))
            levels.append(float(np.sqrt(np.mean(centred ** 2))))
    return float(np.median(levels)) if levels else None


def stability_from_quality(summary: Optional[dict[str, Any]]) -> Optional[str]:
    """Whether the speed held across the record, read off the quality verdict.

    None when nothing assessed it -- which is not 'steady'. The steadiness
    check stands down on records too short to judge, and reporting that as
    steady would let a capture taken during a speed change into a baseline
    that assumes one speed.
    """
    if not summary:
        return None
    assessed = False
    for assessment in (summary.get("channels") or {}).values():
        for check in assessment.get("checks", []):
            if check.get("check") != "unstable_speed":
                continue
            if not check.get("applicable", True):
                continue
            assessed = True
            if not check.get("passed", True):
                return "unstable"
    return "steady" if assessed else None


def persist_mode(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    equipment_id: Optional[UUID],
    channels: dict[str, list[float]],
    shaft_hz: Optional[float] = None,
    shaft_usable: bool = False,
    shaft_source: Optional[str] = None,
    quality_summary: Optional[dict[str, Any]] = None,
) -> ModeVerdict:
    """Decide and store the operating mode for one capture."""
    try:
        # Section 4.1's switch. Checked here rather than at the caller so
        # there is one place it can be forgotten, and a disabled engine
        # still records *why* nothing was decided.
        from app.services.general_settings import settings_for
        general = settings_for(db, equipment_id)
        if not general.mode_detection_enabled:
            return ModeVerdict(
                is_unknown=True, confidence=0.0,
                reason=(
                    f"Mode detection is switched off for this machine "
                    f"({general.source} setting)"
                    + (f": {general.notes}" if general.notes else ".")
                    + " No mode was decided, which is different from a "
                      "capture that could not be placed in one."))

        bands = load_bands(db, equipment_id) if equipment_id else []

        # The two inputs the transient modes need. Both already existed --
        # the previous capture is a row away and the rated speed is on the
        # equipment record -- they were simply never passed, which is why
        # startup, shutdown and idle were undetectable rather than wrong.
        previous = db.execute(text("""
            SELECT m.shaft_hz
              FROM capture_operating_modes m
              JOIN sensor_data_uploads u ON u.id = m.upload_id
             WHERE u.sensor_id = :s AND u.id <> :u AND m.shaft_hz IS NOT NULL
             ORDER BY u.created_at DESC LIMIT 1
        """), {"s": str(sensor_id), "u": str(upload_id)}).scalar()

        rated_rpm = None
        if equipment_id:
            rated_rpm = db.execute(text(
                "SELECT rated_rpm FROM equipment_masters WHERE id = :e"),
                {"e": str(equipment_id)}).scalar()

        verdict = detect_mode(
            bands,
            shaft_hz=shaft_hz,
            shaft_usable=shaft_usable,
            shaft_source=shaft_source,
            overall_level_g=overall_level(channels),
            stability=stability_from_quality(quality_summary),
            previous_shaft_hz=float(previous) if previous else None,
            rated_shaft_hz=(float(rated_rpm) / 60.0) if rated_rpm else None,
        )
    except Exception:
        logger.exception("Mode detection failed for upload %s", upload_id)
        return ModeVerdict(reason="Mode detection failed; treated as unknown.")

    try:
        db.execute(text(f"DELETE FROM {TABLE} WHERE upload_id = :u"),
                   {"u": str(upload_id)})
        db.execute(text(f"""
            INSERT INTO {TABLE}
                (upload_id, sensor_id, mode_id, label, is_unknown, confidence,
                 shaft_hz, shaft_source, overall_level, stability, reason,
                 engine_version)
            VALUES (:u, :s, :mode_id, :label, :is_unknown, :confidence,
                    :shaft_hz, :shaft_source, :overall_level, :stability,
                    :reason, :version)
        """), {
            "u": str(upload_id), "s": str(sensor_id),
            "mode_id": verdict.mode_id, "label": verdict.label,
            "is_unknown": verdict.is_unknown, "confidence": verdict.confidence,
            "shaft_hz": verdict.shaft_hz, "shaft_source": verdict.shaft_source,
            "overall_level": verdict.overall_level,
            "stability": verdict.stability, "reason": verdict.reason,
            "version": ENGINE_VERSION,
        })
    except Exception:
        logger.exception("Could not store the mode for upload %s", upload_id)

    if verdict.label == UNKNOWN:
        logger.info("Upload %s: mode unknown -- %s", upload_id, verdict.reason)
    return verdict


def equipment_for_sensor(db: Session, sensor_id: UUID) -> Optional[UUID]:
    """Which machine a sensor is bolted to, or None."""
    return db.execute(text(
        "SELECT equipment_id FROM sensor_configurations WHERE id = :s"),
        {"s": str(sensor_id)}).scalar()
