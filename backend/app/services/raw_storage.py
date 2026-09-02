"""Persist and load raw snapshots from the database (migration 018).

Before this module a raw snapshot lived only on disk. The samples are now also
rows in `raw_vibration_captures` / `raw_vibration_channels`, stored as Postgres
`float8[]` so the write stays fast.

The disk files are still written and are still the fallback: every snapshot
ingested before migration 018 has no rows here, and must keep reading. So
`load_capture` returns None rather than raising when a capture is absent, and
callers fall through to `_load_parsed_for_upload`.
"""
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.measurement import RawVibrationCapture, RawVibrationChannel


def store_capture(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    parsed: dict[str, Any],
    sample_rate_hz: float,
    start_epoch_s: float | None,
    timebase_unit: str,
) -> RawVibrationCapture:
    """Write one snapshot's channels as array rows.

    `parsed` is the project's standard structure: `channels` maps "ch0", "ch1", …
    to equal-length lists of floats.

    Replaces any existing capture for this upload so a retried ingest cannot
    leave two copies. Does not commit — the caller owns the transaction, so a
    failure further down rolls this back with everything else.
    """
    existing = (
        db.query(RawVibrationCapture)
        .filter(RawVibrationCapture.upload_id == upload_id)
        .one_or_none()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    stored: dict[str, list[float]] = parsed.get("channels") or {}
    capture = RawVibrationCapture(
        upload_id=upload_id,
        sensor_id=sensor_id,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=int(parsed.get("sample_count") or 0),
        channel_count=int(parsed.get("channel_count") or len(stored)),
        start_epoch_s=start_epoch_s,
        timebase_unit=timebase_unit,
    )
    db.add(capture)
    db.flush()

    for key, values in stored.items():
        if not key.startswith("ch") or not key[2:].isdigit():
            continue
        db.add(
            RawVibrationChannel(
                capture_id=capture.id,
                channel_index=int(key[2:]),
                samples=[float(v) for v in values],
            )
        )
    db.flush()
    return capture


def load_capture(db: Session, upload_id: UUID) -> dict[str, Any] | None:
    """Rebuild the parsed structure for one upload, or None if not stored here.

    The returned shape matches what `_load_parsed_for_upload` produces from
    disk, so every existing reader works unchanged. Timestamps are regenerated
    from the stored rate — acquisition is uniform, so they are implied rather
    than kept.
    """
    capture = (
        db.query(RawVibrationCapture)
        .filter(RawVibrationCapture.upload_id == upload_id)
        .one_or_none()
    )
    if capture is None:
        return None

    rows = (
        db.query(RawVibrationChannel)
        .filter(RawVibrationChannel.capture_id == capture.id)
        .order_by(RawVibrationChannel.channel_index)
        .all()
    )
    if not rows:
        return None

    channels = {f"ch{row.channel_index}": list(row.samples or []) for row in rows}
    count = int(capture.sample_count or 0)
    rate = float(capture.sample_rate_hz or 0.0)
    step = 1.0 / rate if rate > 0 else 0.0

    return {
        "timestamps": [i * step for i in range(count)],
        "channels": channels,
        "sample_count": count,
        "channel_count": int(capture.channel_count or len(channels)),
        "sampling_rate_hz": rate,
        "start_epoch_s": capture.start_epoch_s,
        "timebase_unit": capture.timebase_unit,
    }


def capture_summary(db: Session, upload_id: UUID) -> RawVibrationCapture | None:
    """The capture row without its sample arrays — for listings and headers."""
    return (
        db.query(RawVibrationCapture)
        .filter(RawVibrationCapture.upload_id == upload_id)
        .one_or_none()
    )
