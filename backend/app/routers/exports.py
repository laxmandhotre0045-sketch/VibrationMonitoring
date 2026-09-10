"""Sensor inventory and per-sensor CSV export.

Read-only, so every route sits behind ``get_current_user`` rather than
``require_write_access`` — a read-only ``user`` account is meant to be able to
pull its own data out.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.services.sensor_export import (
    DEFAULT_MAX_CAPTURES,
    build_sensor_rows,
    export_filename,
    list_sensors,
    rows_to_csv,
)

router = APIRouter(
    prefix="/api/v1/sensors",
    tags=["Sensor Export"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", summary="List every sensor with the machine it is mounted on")
def get_sensors(
    filter_text: str = Query("", description="Optional words to narrow the list"),
    db: Session = Depends(get_db),
):
    items = list_sensors(db, filter_text)
    return {"count": len(items), "items": items}


@router.get(
    "/{sensor_id}/export",
    summary="Sensor history as JSON rows, with a summary",
)
def export_sensor_json(
    sensor_id: UUID,
    from_date: date | None = Query(None, description="Include captures on or after this date"),
    to_date: date | None = Query(None, description="Include captures on or before this date"),
    max_captures: int = Query(DEFAULT_MAX_CAPTURES, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """The same data the CSV carries, for the UI to render as a table."""
    try:
        rows, summary = build_sensor_rows(
            db,
            sensor_id,
            from_date=from_date,
            to_date=to_date,
            max_captures=max_captures,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"summary": summary, "rows": rows}


@router.get(
    "/{sensor_id}/export.csv",
    response_class=PlainTextResponse,
    summary="Sensor history as a downloadable CSV",
)
def export_sensor_csv(
    sensor_id: UUID,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    max_captures: int = Query(DEFAULT_MAX_CAPTURES, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    try:
        rows, summary = build_sensor_rows(
            db,
            sensor_id,
            from_date=from_date,
            to_date=to_date,
            max_captures=max_captures,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PlainTextResponse(
        content=rows_to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(summary)}"'
        },
    )
