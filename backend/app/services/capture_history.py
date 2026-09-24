"""When data arrived, and what it has been doing — MOM items 10 and 12.

Item 10 asks for the dates of data entries and a clear statement of when the
most recent one was. Item 12 asks for 7-day and 30-day summary views.

Both are about elapsed time, and that makes the honest treatment of *partial*
coverage the whole design problem. A card reading "7 days — 20 captures" is
true and useless: those twenty captures might span a week or forty minutes, and
the reader cannot tell which. Worse, a trend arrow drawn through forty minutes
of data is not a weekly trend at all, it is noise with a direction.

So every window here reports what it actually covers — how many distinct days
saw data, the real span, and where the gaps are — and a trend is withheld
outright unless the data underneath it could support one. `trend` is None with
a stated reason far more often than it is a number, and that is correct.

Channel RMS is computed in Postgres rather than in Python. Each capture holds
eight arrays of ~13,888 float8; pulling those across the wire to average them
would move roughly a megabyte per capture to produce eight numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Windows the MOM asks for. Kept as data so adding a 90-day card later is a
#: list entry rather than a new code path.
WINDOW_DAYS = (7, 30)

#: A trend needs both enough points and enough elapsed time. Six captures taken
#: over forty minutes describe forty minutes, however many of them there are —
#: so the span test is the one that actually protects the reader.
MIN_POINTS_FOR_TREND = 6
MIN_SPAN_FRACTION = 0.10          # of the window, e.g. 16.8 h within 7 days

#: Below this the direction is reported as "flat". Machine vibration wanders by
#: a few percent between captures with nothing changing; calling that a rise
#: would put an arrow on every card permanently.
FLAT_BAND = 0.05                  # +/-5% of the window's mean


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Rows written by different paths differ in tzinfo; comparing a naive to
    an aware datetime raises, and that would take the whole card down."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class ChannelTrend:
    channel_index: int
    rms_mean: float
    rms_min: float
    rms_max: float
    #: Fractional change from the first half of the window to the second, or
    #: None when the data cannot support the claim.
    trend: Optional[float] = None
    direction: str = "unknown"
    trend_blocked_reason: Optional[str] = None


@dataclass
class Window:
    days: int
    captures: int
    active_days: int
    first_at: Optional[datetime]
    last_at: Optional[datetime]
    span_hours: float
    #: What fraction of the window actually contains data. This is the number
    #: that stops "7 days" being read as "a week of monitoring".
    coverage_fraction: float
    channels: list[ChannelTrend] = field(default_factory=list)
    note: Optional[str] = None


def _sensor_ids_for(db: Session, sensor_id: Optional[UUID]) -> list[str]:
    if sensor_id:
        return [str(sensor_id)]
    rows = db.execute(text(
        "SELECT DISTINCT sensor_id::text FROM raw_vibration_captures"
    )).fetchall()
    return [r[0] for r in rows]


def last_entry(db: Session, sensor_id: Optional[UUID] = None) -> Optional[dict[str, Any]]:
    """The most recent capture, with everything needed to say so in words.

    MOM item 10's "clearly identify when the most recent data entry was made"
    needs more than a timestamp: a date alone does not tell a reader whether
    the feed is alive. The age in seconds is what answers that, so it is
    computed here rather than left to a client whose clock may differ.
    """
    clause = "WHERE c.sensor_id = :sid" if sensor_id else ""
    row = db.execute(text(f"""
        SELECT c.id::text, c.created_at, c.sample_count, c.channel_count,
               c.sample_rate_hz, u.original_filename, u.id::text AS upload_id,
               e.machine_name, s.mounting_location, s.orientation
          FROM raw_vibration_captures c
          JOIN sensor_data_uploads u ON u.id = c.upload_id
          JOIN sensor_configurations s ON s.id = c.sensor_id
          JOIN equipment_masters e ON e.id = s.equipment_id
          {clause}
         ORDER BY c.created_at DESC
         LIMIT 1
    """), {"sid": str(sensor_id) if sensor_id else None}).fetchone()
    if not row:
        return None

    at = _as_aware(row.created_at)
    return {
        "capture_id": row[0],
        "upload_id": row.upload_id,
        "at": at,
        "age_seconds": (_utcnow() - at).total_seconds() if at else None,
        "machine_name": row.machine_name,
        "sensor_location": f"{row.mounting_location} ({row.orientation})",
        "original_filename": row.original_filename,
        "sample_count": row.sample_count,
        "channel_count": row.channel_count,
        "sample_rate_hz": row.sample_rate_hz,
    }


def entries_by_date(db: Session, days: int = 30,
                    sensor_id: Optional[UUID] = None) -> list[dict[str, Any]]:
    """One row per calendar day that has data — item 10's "dates of entries".

    Days with no data are omitted rather than returned as zeros. A caller
    drawing a calendar wants to know which days are blank, and can see that
    from the dates that are missing; padding them here would make an empty
    month indistinguishable from a busy one in a list length check.
    """
    clause = "AND c.sensor_id = :sid" if sensor_id else ""
    rows = db.execute(text(f"""
        SELECT (c.created_at AT TIME ZONE 'UTC')::date AS day,
               COUNT(*) AS n,
               MIN(c.created_at) AS first_at,
               MAX(c.created_at) AS last_at
          FROM raw_vibration_captures c
         WHERE c.created_at >= :since {clause}
         GROUP BY day
         ORDER BY day DESC
    """), {"since": _utcnow() - timedelta(days=days),
           "sid": str(sensor_id) if sensor_id else None}).fetchall()
    return [{
        "date": r.day.isoformat(),
        "count": int(r.n),
        "first_at": _as_aware(r.first_at),
        "last_at": _as_aware(r.last_at),
    } for r in rows]


def _channel_rms(db: Session, since: datetime, sensor_id: Optional[UUID]
                 ) -> list[tuple[int, datetime, float]]:
    """(channel_index, captured_at, ac_rms) for every channel in the window.

    Reads the summary column written when the capture was stored (migration
    019). The first version of this unnested the stored float8[] and computed
    sqrt(avg(v*v)) on every dashboard load: correct, and 0.113 s per capture,
    which at a two-minute capture interval is 81 s after one day and 40 minutes
    over a 30-day window. The statistic never changes, so it is computed once.

    AC RMS rather than raw RMS: the raw figure is dominated by each sensor's
    standing DC bias -- ch7 sits near -0.145 g -- so a trend on it tracks bias
    drift rather than vibration. Rows predating the backfill are NULL and are
    skipped rather than read as zero, which would show as a collapse in level.
    """
    clause = "AND c.sensor_id = :sid" if sensor_id else ""
    rows = db.execute(text(f"""
        SELECT ch.channel_index, c.created_at, ch.ac_rms
          FROM raw_vibration_channels ch
          JOIN raw_vibration_captures c ON c.id = ch.capture_id
         WHERE c.created_at >= :since AND ch.ac_rms IS NOT NULL {clause}
         ORDER BY ch.channel_index, c.created_at
    """), {"since": since, "sid": str(sensor_id) if sensor_id else None}).fetchall()
    return [(int(r.channel_index), _as_aware(r.created_at), float(r.ac_rms))
            for r in rows]


def _trend_for(points: list[tuple[datetime, float]], days: int,
               span_hours: float) -> tuple[Optional[float], str, Optional[str]]:
    """Fractional change between the two halves of the window.

    A first-half/second-half comparison rather than a least-squares slope: the
    reader is being shown a card, not a regression, and the halves answer the
    question a card asks -- "higher or lower than it was" -- without implying a
    precision the sampling does not have.
    """
    if len(points) < MIN_POINTS_FOR_TREND:
        return None, "unknown", (
            f"only {len(points)} capture(s); {MIN_POINTS_FOR_TREND} needed")

    required_hours = days * 24 * MIN_SPAN_FRACTION
    if span_hours < required_hours:
        return None, "unknown", (
            f"data spans {span_hours:.1f} h of the {days}-day window; "
            f"{required_hours:.0f} h needed before a trend means anything")

    mid = len(points) // 2
    first = [v for _, v in points[:mid]]
    second = [v for _, v in points[mid:]]
    a = sum(first) / len(first)
    b = sum(second) / len(second)
    if a <= 0:
        return None, "unknown", "baseline is zero"

    change = (b - a) / a
    if abs(change) < FLAT_BAND:
        return change, "flat", None
    return change, ("rising" if change > 0 else "falling"), None


def window_summary(db: Session, days: int,
                   sensor_id: Optional[UUID] = None) -> Window:
    since = _utcnow() - timedelta(days=days)
    clause = "AND c.sensor_id = :sid" if sensor_id else ""
    agg = db.execute(text(f"""
        SELECT COUNT(*) AS n,
               MIN(c.created_at) AS first_at,
               MAX(c.created_at) AS last_at,
               COUNT(DISTINCT (c.created_at AT TIME ZONE 'UTC')::date) AS active_days
          FROM raw_vibration_captures c
         WHERE c.created_at >= :since {clause}
    """), {"since": since, "sid": str(sensor_id) if sensor_id else None}).fetchone()

    first_at = _as_aware(agg.first_at)
    last_at = _as_aware(agg.last_at)
    span_hours = ((last_at - first_at).total_seconds() / 3600.0
                  if first_at and last_at else 0.0)
    coverage = span_hours / (days * 24.0) if days else 0.0

    win = Window(
        days=days,
        captures=int(agg.n or 0),
        active_days=int(agg.active_days or 0),
        first_at=first_at,
        last_at=last_at,
        span_hours=span_hours,
        coverage_fraction=min(coverage, 1.0),
    )
    if win.captures == 0:
        win.note = f"No captures in the last {days} days."
        return win

    # Said plainly on the card, because "20 captures" over forty minutes and
    # over a week look identical otherwise.
    if coverage < 0.5:
        win.note = (
            f"{win.captures} capture(s) covering {span_hours:.1f} h of the "
            f"{days}-day window ({coverage * 100:.1f}%). Figures describe that "
            f"period, not the full window."
        )

    by_channel: dict[int, list[tuple[datetime, float]]] = {}
    for idx, at, rms in _channel_rms(db, since, sensor_id):
        by_channel.setdefault(idx, []).append((at, rms))

    for idx in sorted(by_channel):
        pts = sorted(by_channel[idx], key=lambda p: p[0])
        values = [v for _, v in pts]
        change, direction, blocked = _trend_for(pts, days, span_hours)
        win.channels.append(ChannelTrend(
            channel_index=idx,
            # AC rms -- vibration with the DC bias removed.
            rms_mean=sum(values) / len(values),
            rms_min=min(values),
            rms_max=max(values),
            trend=change,
            direction=direction,
            trend_blocked_reason=blocked,
        ))
    return win


def history(db: Session, sensor_id: Optional[UUID] = None) -> dict[str, Any]:
    """Everything items 10 and 12 need, in one round trip."""
    return {
        "generated_at": _utcnow(),
        "last_entry": last_entry(db, sensor_id),
        "entries_by_date": entries_by_date(db, days=max(WINDOW_DAYS), sensor_id=sensor_id),
        "windows": [window_summary(db, d, sensor_id) for d in WINDOW_DAYS],
    }
