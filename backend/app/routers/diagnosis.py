"""Phase 3 over HTTP: the fault, the zone, the score and the proof.

Everything Phase 3 built was reachable only from inside the ingestion
pipeline. A finding sitting in a table nobody can query is a finding nobody
can act on, so this is the surface.

Four endpoints, and the shape of each is set by one rule: **an answer the
platform could not compute is returned as an absence with a reason, never
as a neutral value.** No findings comes back with the resolution verdict
attached, so "we found nothing" and "we could not have seen it" are
different responses. Health comes back as `null` with a sentence rather
than 100. An ambiguous ISO grade comes back as every table that could
apply rather than the most likely one.

The plot-evidence endpoint (VIK-059) is what turns the rest into something
checkable: given a fault, which screen to open and what to look for on it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.iso_grade import grade_spectrum
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.services.fault_storage import open_findings
from app.services.fleet_storage import fleet as fleet_summary
from app.services.fleet_storage import operator_view
from app.services import reports as report_service
from app.services.health_storage import (
    capture_symptoms,
    latest_upload,
    plot_evidence_table,
    plots_for,
    sensor_health,
    sensor_reliability,
    sensor_rul,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/diagnosis",
    tags=["Diagnosis"],
    dependencies=[Depends(get_current_user)],
)


def _machine_for(db: Session, sensor_id: UUID) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT e.machine_name, e.machine_type, e.machine_criticality,
               e.rated_power_kw, e.foundation_type, e.drive_type
          FROM sensor_configurations s
          LEFT JOIN equipment_masters e ON e.id = s.equipment_id
         WHERE s.id = :s
    """), {"s": str(sensor_id)}).mappings().fetchone()
    return dict(row) if row else {}


def _require_sensor(db: Session, sensor_id: UUID) -> None:
    exists = db.execute(
        text("SELECT 1 FROM sensor_configurations WHERE id = :s"),
        {"s": str(sensor_id)}).fetchone()
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"No sensor {sensor_id}")


@router.get("/findings", summary="What this machine is thought to be doing")
def findings(
    sensor_id: UUID = Query(..., description="Sensor to diagnose"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Open findings, worst first, each with the plots that would prove it.

    An empty list is not good news on its own, so the resolution verdict
    from the most recent finding travels beside it. On this gateway a
    0.278 s record cannot separate the outer-race frequency from the third
    shaft harmonic, and a caller that renders an empty list as a healthy
    machine would be wrong in exactly the way this phase exists to prevent.
    """
    _require_sensor(db, sensor_id)
    rows = open_findings(db, sensor_id)

    for row in rows:
        row["plots"] = plots_for(db, row["fault_key"])

    resolution = next((r.get("resolution") for r in rows if r.get("resolution")),
                      None)
    if resolution is None:
        recent = db.execute(text("""
            SELECT resolution FROM fault_findings
             WHERE sensor_id = :s ORDER BY last_seen_at DESC LIMIT 1
        """), {"s": str(sensor_id)}).fetchone()
        resolution = recent[0] if recent else None

    if rows:
        reason = (f"{len(rows)} finding(s) are open on this machine.")
    elif resolution and not resolution.get("usable"):
        reason = ("No fault is open on this machine, but that is not "
                  "evidence it is healthy: "
                  + (resolution.get("reason") or ""))
    elif resolution:
        reason = ("No fault is open on this machine, and the spectrum "
                  "could have shown one.")
    else:
        reason = ("No capture on this machine has been through fault "
                  "ranking yet, so nothing has been looked for.")

    return {"sensor_id": str(sensor_id), "findings": rows,
            "resolution": resolution, "count": len(rows), "reason": reason}


@router.get("/health", summary="A health score built from what is known")
def health(
    sensor_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """VIK-055. `score` may be null, and null is the honest answer for a
    machine nothing has been measured on."""
    _require_sensor(db, sensor_id)
    machine = _machine_for(db, sensor_id)
    verdict = sensor_health(db, sensor_id,
                            criticality=machine.get("machine_criticality"))
    verdict["machine_name"] = machine.get("machine_name")
    return verdict


@router.get("/reliability",
            summary="How dependable this machine's record is (12.2)")
def reliability(
    sensor_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section 12.2, and deliberately not the same number as health.

    Health says how the machine is now; reliability says how much it can be
    leaned on. A pump repaired four times this year can read perfectly
    healthy this morning and still be the one you would not stake a
    shutdown window on.

    A machine with a short record is reported as unproven with its ceiling
    stated, rather than as reliable -- every history-based input reads
    perfectly on an asset nobody has watched yet.
    """
    _require_sensor(db, sensor_id)
    machine = _machine_for(db, sensor_id)
    row = db.execute(text("""
        SELECT e.last_maintenance_date
          FROM sensor_configurations s
          LEFT JOIN equipment_masters e ON e.id = s.equipment_id
         WHERE s.id = :s
    """), {"s": str(sensor_id)}).fetchone()

    verdict = sensor_reliability(
        db, sensor_id, criticality=machine.get("machine_criticality"),
        last_maintenance=row[0] if row else None)
    verdict["machine_name"] = machine.get("machine_name")
    return verdict


@router.get("/operator", summary="Is it running, and is it alright (19.1)")
def operator(
    plant_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section 19.1, for somebody walking the plant rather than sitting
    with it. One short action sentence per machine.

    Temperature is one of the six fields asked for and nothing on this
    platform measures one, so it is returned as unavailable with the reason
    rather than omitted.
    """
    return operator_view(db, plant_name=plant_name)


@router.get("/rul", summary="Remaining useful life, or why not (13)")
def rul(
    sensor_id: UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section 13, which opens with the condition rather than the sum:
    "RUL should be provided only when enough historical trend data is
    available."

    Expect the refusal. This gateway has five days of history against the
    thirty the shortest credible extrapolation needs, and a failure date
    fitted to five days is arithmetic anybody can do and nobody should
    trust. `available` is false and `reason` says what is missing.
    """
    _require_sensor(db, sensor_id)
    verdict = sensor_rul(db, sensor_id)
    machine = _machine_for(db, sensor_id)
    verdict["machine_name"] = machine.get("machine_name")
    return verdict


@router.get("/fleet", summary="The whole site in one picture (19.3)")
def fleet(
    plant_name: Optional[str] = Query(
        None, description="Restrict to one plant."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section 19.3's management view, and fleet-level intelligence.

    Machines that cannot be scored are excluded from the site averages
    rather than counted as healthy, and the list of them travels with the
    number. An average computed from nine of twenty machines that does not
    say so is worse than no average.
    """
    return fleet_summary(db, plant_name=plant_name)


@router.get("/iso", summary="ISO 10816-3 zone, or every zone it could be")
def iso(
    sensor_id: UUID = Query(...),
    channel: int = Query(0, ge=0, description="Channel to grade"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """VIK-056. Where the machine record leaves the group ambiguous, every
    applicable table is returned with what is missing -- except where they
    all agree, in which case the gap does not change the answer and the
    zone is reported."""
    _require_sensor(db, sensor_id)
    machine = _machine_for(db, sensor_id)
    upload = latest_upload(db, sensor_id)
    if not upload:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="No capture exists for this sensor.")

    row = db.execute(text("""
        SELECT u.parsed_data_path, p.sampling_rate_hz
          FROM sensor_data_uploads u
          LEFT JOIN plot_configurations p ON p.sensor_id = u.sensor_id
         WHERE u.id = :u
    """), {"u": str(upload["id"])}).mappings().fetchone()

    if not row or not row["parsed_data_path"] or not row["sampling_rate_hz"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=("The most recent capture has no parsed samples or no "
                    "sampling rate on record, so no velocity can be "
                    "computed from it."))

    try:
        from app.services.feature_extraction import _compute_fft_magnitudes, _to_array
        from app.services.plot_generator import load_parsed_data

        parsed = load_parsed_data(row["parsed_data_path"])
        samples = (parsed.get("channels") or {}).get(f"ch{channel}")
        if not samples or len(samples) < 4:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Channel {channel} has no samples in this capture.")
        array = _to_array(samples)
        freqs, mags = _compute_fft_magnitudes(
            array, float(row["sampling_rate_hz"]))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Could not build a spectrum for sensor %s", sensor_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The capture could not be read.")

    power = machine.get("rated_power_kw")
    verdict = grade_spectrum(
        freqs, mags, samples=array,
        machine_type=machine.get("machine_type"),
        power_kw=float(power) if power is not None else None,
        foundation=machine.get("foundation_type"),
        integrated_driver=bool(
            "integrated" in str(machine.get("drive_type") or "").lower()),
    )
    payload = verdict.as_dict()
    payload.update({"sensor_id": str(sensor_id), "channel": channel,
                    "upload_id": str(upload["id"]),
                    "machine_name": machine.get("machine_name")})
    return payload


@router.get("/symptoms", summary="What the signal is doing (VIK-051)")
def symptoms(
    sensor_id: UUID = Query(...),
    upload_id: Optional[UUID] = Query(
        None, description="A specific capture; omit for the most recent."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Observations, separate from any fault the rules did or did not name.

    This is the endpoint that matters most on this gateway. No capture here
    establishes a shaft speed, so no rule in the fault table can be
    evaluated and `/findings` is empty on every machine. The symptoms are
    the only thing the platform can currently say about a signal, and they
    say it with the numbers attached.
    """
    _require_sensor(db, sensor_id)
    return capture_symptoms(db, sensor_id, upload_id)


@router.get("/reports", summary="The nine report types (17.2)")
def report_types() -> dict[str, Any]:
    """Section 17.2's list, with what each covers."""
    return {"reports": report_service.available_reports()}


@router.get("/reports/machine", summary="One machine's report (17.1)")
def machine_report(
    sensor_id: UUID = Query(...),
    report_type: str = Query("weekly_machine_health"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Section 17.1's eighteen items for one machine.

    Sections that could not be filled are present with the reason rather
    than omitted. A report that silently drops what it could not gather
    reads as a clean bill of health, and on this gateway most of it cannot
    be gathered.
    """
    _require_sensor(db, sensor_id)
    try:
        return report_service.machine_report(
            db, sensor_id=sensor_id, report_type=report_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/reports/fleet", summary="A fleet-scoped report (17.2)")
def fleet_report(
    report_type: str = Query("fleet_health"),
    plant_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return report_service.fleet_report(
            db, report_type=report_type, plant_name=plant_name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/governance", summary="Model, baseline and feature versions (22)")
def governance(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Section 22, including whether its closing line is being honoured.

    `compliant` is false when the code is running a version the registry
    has never heard of -- which is precisely "a model changed silently".
    """
    from app.services.governance import summary as governance_summary
    return governance_summary(db)


@router.get("/plot-evidence",
            summary="Which plot proves which fault (VIK-059)")
def plot_evidence(
    fault_key: Optional[str] = Query(
        None, description="One fault; omit for the whole table."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reference material, editable without a deploy.

    Every plot named here is one the frontend already renders, so a caller
    can turn a row into a link rather than into a feature request.
    """
    if fault_key:
        rows = plots_for(db, fault_key)
        if not rows:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No plot guidance is recorded for {fault_key!r}.")
        return {"fault_key": fault_key, "plots": rows}

    table = plot_evidence_table(db)
    return {"faults": table, "count": len(table),
            "rows": sum(len(v) for v in table.values())}
