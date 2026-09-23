"""Build and store learned baselines from capture history — VIK-025.

Reads what every feature has actually done over a window of captures, and
writes the robust statistics to `feature_baseline_stats`.

Two things it deliberately does not do.

**It does not use `sensor_baselines`.** That table holds the known-good
reference capture and keeps that job. The roadmap records what relying on it
alone costs: the current "healthy baseline" is a copy of the very file being
compared against it, and 144 readings would turn green the moment somebody
nominated it. This is the learned normal beside that, not a replacement.

**It does not quietly rebuild in place.** A reset starts a new version
(VIK-026), because a finding has to be traceable to the baseline that
produced it -- and a baseline edited under a finding silently rewrites what
that finding meant.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.baseline import (
    MIN_SAMPLES,
    BaselineStats,
    Observation,
    build_baseline,
)

logger = logging.getLogger(__name__)

TABLE = "feature_baseline_stats"


def load_history(
    db: Session,
    sensor_id: UUID,
    *,
    days: Optional[int] = None,
    limit_captures: Optional[int] = None,
) -> dict[tuple[int, str], list[Observation]]:
    """Every stored feature value for one sensor, keyed by channel and code.

    Each value carries the quality level of the channel it came from, so the
    baseline engine can keep an Invalid capture out of what the machine is
    expected to look like. Joined here rather than filtered here: deciding
    what is admissible is the engine's job, and doing it in SQL would hide
    the exclusion count the engine reports.
    """
    window = "AND u.created_at >= now() - make_interval(days => :days)" if days else ""
    rows = db.execute(text(f"""
        SELECT f.channel, f.feature_code, f.value, u.created_at,
               -- 'unknown', never 'high'. A capture nobody assessed is not
               -- a capture that passed, and defaulting it to the best grade
               -- is how the nine synthetic uploads on this platform -- which
               -- predate the quality engine and have no samples left to
               -- assess -- came to be admitted as exemplary.
               COALESCE(q.level, 'unknown') AS quality_level
          FROM measurement_channel_features f
          JOIN sensor_data_uploads u ON u.id = f.upload_id
          LEFT JOIN data_quality_assessments q
                 ON q.upload_id = f.upload_id AND q.channel = f.channel
         WHERE f.sensor_id = :sensor {window}
         ORDER BY u.created_at
    """), {"sensor": str(sensor_id), **({"days": days} if days else {})}).fetchall()

    history: dict[tuple[int, str], list[Observation]] = {}
    for row in rows:
        key = (int(row.channel), row.feature_code)
        history.setdefault(key, []).append(
            Observation(float(row.value), row.created_at, row.quality_level))

    if limit_captures:
        for key, observations in history.items():
            history[key] = observations[-limit_captures:]
    return history


def next_version(db: Session, sensor_id: UUID) -> int:
    current = db.execute(text(f"""
        SELECT COALESCE(MAX(baseline_version), 0) FROM {TABLE}
         WHERE sensor_id = :s
    """), {"s": str(sensor_id)}).scalar()
    return int(current or 0) + 1


def store(db: Session, stats: BaselineStats, version: int) -> bool:
    """Write one baseline. Refusals are not written.

    A row that says "no baseline" would have to carry zeros in columns the
    table requires to be real numbers, and a reader joining to it would find
    a median of zero for a machine that has none. The absence of a row is
    the honest representation, and the engine's reason travels with the
    response instead.
    """
    if not stats.available:
        return False
    db.execute(text(f"""
        INSERT INTO {TABLE}
            (sensor_id, channel, feature_code, mode_id, median, mad,
             robust_sigma, p05, p50, p95, ewma, sample_count,
             window_start, window_end, baseline_version, is_active)
        VALUES (:sensor_id, :channel, :feature_code, NULL, :median, :mad,
                :robust_sigma, :p05, :p50, :p95, :ewma, :sample_count,
                :window_start, :window_end, :version, true)
        ON CONFLICT (sensor_id, channel, feature_code, mode_id, baseline_version)
        DO UPDATE SET
            median = EXCLUDED.median, mad = EXCLUDED.mad,
            robust_sigma = EXCLUDED.robust_sigma,
            p05 = EXCLUDED.p05, p50 = EXCLUDED.p50, p95 = EXCLUDED.p95,
            ewma = EXCLUDED.ewma, sample_count = EXCLUDED.sample_count,
            window_start = EXCLUDED.window_start,
            window_end = EXCLUDED.window_end,
            computed_at = now()
    """), {
        "sensor_id": stats.sensor_id, "channel": stats.channel,
        "feature_code": stats.feature_code, "median": stats.median,
        "mad": stats.mad, "robust_sigma": stats.robust_sigma,
        "p05": stats.p05, "p50": stats.p50, "p95": stats.p95,
        "ewma": stats.ewma, "sample_count": stats.sample_count,
        "window_start": stats.window_start, "window_end": stats.window_end,
        "version": version,
    })
    return True


def rebuild_for_sensor(
    db: Session,
    sensor_id: UUID,
    *,
    days: Optional[int] = None,
    min_samples: int = MIN_SAMPLES,
    new_version: bool = False,
) -> dict[str, Any]:
    """Build every baseline this sensor has enough history for.

    `new_version` starts a fresh version and retires the old one rather than
    editing it. Anything already recorded against the previous version keeps
    meaning what it meant.
    """
    history = load_history(db, sensor_id, days=days)
    if not history:
        return {"sensor_id": str(sensor_id), "stored": 0, "refused": 0,
                "version": 0, "reason": "no feature history for this sensor"}

    version = next_version(db, sensor_id) if new_version else max(
        1, next_version(db, sensor_id) - 1)

    if new_version:
        db.execute(text(f"UPDATE {TABLE} SET is_active = false "
                        f"WHERE sensor_id = :s"), {"s": str(sensor_id)})

    stored = refused = 0
    refusals: dict[str, int] = {}
    for (channel, code), observations in sorted(history.items()):
        stats = build_baseline(str(sensor_id), channel, code, observations,
                               min_samples=min_samples)
        if store(db, stats, version):
            stored += 1
        else:
            refused += 1
            refusals[code] = refusals.get(code, 0) + 1

    logger.info("Baselines for sensor %s v%d: %d stored, %d refused",
                sensor_id, version, stored, refused)
    return {
        "sensor_id": str(sensor_id), "version": version,
        "stored": stored, "refused": refused,
        "captures_in_window": max((len(o) for o in history.values()), default=0),
        "refused_features": sorted(refusals),
    }


def load_baseline_map(db: Session, sensor_id: UUID,
                      version: Optional[int] = None) -> dict[tuple[int, str], dict]:
    """The active baselines, keyed the way a feature row is."""
    clause = "AND baseline_version = :v" if version else "AND is_active"
    rows = db.execute(text(f"""
        SELECT channel, feature_code, median, mad, robust_sigma,
               p05, p50, p95, ewma, sample_count, baseline_version
          FROM {TABLE} WHERE sensor_id = :s {clause}
    """), {"s": str(sensor_id), **({"v": version} if version else {})}
    ).mappings().fetchall()
    return {(row["channel"], row["feature_code"]): dict(row) for row in rows}
