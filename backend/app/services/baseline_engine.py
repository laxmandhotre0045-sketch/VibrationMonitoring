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
    AcquisitionShape,
    BaselineStats,
    Observation,
    build_baseline,
)
from app.services import baseline_lifecycle as lifecycle

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
               -- The acquisition shape travels with every value. Half the
               -- features move by a quarter or more when it changes, so a
               -- baseline that mixed two shapes would find every capture
               -- anomalous for a settings change.
               c.sample_rate_hz, c.sample_count,
               -- and the converter setting the channel was measured at, so
               -- a baseline learned at 100 mV/g is not compared with one at
               -- 500. Measured from the samples, not declared.
               q.quantisation_step_g,
               -- and which operating mode the machine was in. A pump at low
               -- load and the same pump at high load produce different
               -- vibration while both are healthy, so a normal that spans
               -- them describes neither (VIK-040).
               m.mode_id AS mode_id,
               -- 'unknown', never 'high'. A capture nobody assessed is not
               -- a capture that passed, and defaulting it to the best grade
               -- is how the nine synthetic uploads on this platform -- which
               -- predate the quality engine and have no samples left to
               -- assess -- came to be admitted as exemplary.
               COALESCE(q.level, 'unknown') AS quality_level
          FROM measurement_channel_features f
          JOIN sensor_data_uploads u ON u.id = f.upload_id
          LEFT JOIN raw_vibration_captures c ON c.upload_id = f.upload_id
          LEFT JOIN data_quality_assessments q
                 ON q.upload_id = f.upload_id AND q.channel = f.channel
          -- `NOT is_unknown` is belt and braces: a check constraint already
          -- forbids a row that is unknown and still names a mode, so the
          -- mode_id on such a row is null either way. Kept because the
          -- intent should be readable here rather than only in the schema.
          LEFT JOIN capture_operating_modes m
                 ON m.upload_id = f.upload_id AND NOT m.is_unknown
         WHERE f.sensor_id = :sensor {window}
         ORDER BY u.created_at
    """), {"sensor": str(sensor_id), **({"days": days} if days else {})}).fetchall()

    history: dict[tuple[int, str], list[Observation]] = {}
    for row in rows:
        key = (int(row.channel), row.feature_code)
        history.setdefault(key, []).append(Observation(
            float(row.value), row.created_at, row.quality_level,
            AcquisitionShape(
                float(row.sample_rate_hz) if row.sample_rate_hz else None,
                int(row.sample_count) if row.sample_count else None,
                float(row.quantisation_step_g)
                if row.quantisation_step_g else None),
            str(row.mode_id) if row.mode_id else None))

    if limit_captures:
        for key, observations in history.items():
            history[key] = observations[-limit_captures:]
    return history


def store(db: Session, stats: BaselineStats, version: int,
          mode_id: Optional[str] = None) -> bool:
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
             window_start, window_end, baseline_version,
             acquisition_sample_rate_hz, acquisition_sample_count,
             confidence, excluded_count, distinct_count, mixed_population,
             other_shape_count, acquisition_step_g, other_step_count)
        VALUES (:sensor_id, :channel, :feature_code, :mode_id, :median, :mad,
                :robust_sigma, :p05, :p50, :p95, :ewma, :sample_count,
                :window_start, :window_end, :version,
                :rate_hz, :samples,
                :confidence, :excluded, :distinct, :mixed, :other_shape,
                :step_g, :other_step)
        ON CONFLICT (sensor_id, channel, feature_code, mode_id, baseline_version)
        DO UPDATE SET
            median = EXCLUDED.median, mad = EXCLUDED.mad,
            robust_sigma = EXCLUDED.robust_sigma,
            p05 = EXCLUDED.p05, p50 = EXCLUDED.p50, p95 = EXCLUDED.p95,
            ewma = EXCLUDED.ewma, sample_count = EXCLUDED.sample_count,
            window_start = EXCLUDED.window_start,
            window_end = EXCLUDED.window_end,
            acquisition_sample_rate_hz = EXCLUDED.acquisition_sample_rate_hz,
            acquisition_sample_count = EXCLUDED.acquisition_sample_count,
            confidence = EXCLUDED.confidence,
            excluded_count = EXCLUDED.excluded_count,
            distinct_count = EXCLUDED.distinct_count,
            mixed_population = EXCLUDED.mixed_population,
            other_shape_count = EXCLUDED.other_shape_count,
            acquisition_step_g = EXCLUDED.acquisition_step_g,
            other_step_count = EXCLUDED.other_step_count,
            computed_at = now()
    """), {
        "mode_id": mode_id,
        "sensor_id": stats.sensor_id, "channel": stats.channel,
        "feature_code": stats.feature_code, "median": stats.median,
        "mad": stats.mad, "robust_sigma": stats.robust_sigma,
        "p05": stats.p05, "p50": stats.p50, "p95": stats.p95,
        "ewma": stats.ewma, "sample_count": stats.sample_count,
        "window_start": stats.window_start, "window_end": stats.window_end,
        "version": version,
        "rate_hz": stats.shape.sample_rate_hz,
        "samples": stats.shape.sample_count,
        # Computed by the engine and, until VIK-027, thrown away here.
        # Recomputing confidence to answer a read would mean rebuilding every
        # baseline from history; mixed_population is the one a reader must
        # not be without, because it marks a row whose percentiles belong to
        # a different population from its median.
        "confidence": stats.confidence,
        "excluded": stats.excluded_count,
        "distinct": stats.distinct_count,
        "mixed": stats.mixed_population,
        "other_shape": stats.other_shape_count,
        "step_g": stats.shape.step_g,
        "other_step": stats.other_step_count,
    })
    return True


def compute_into_version(
    db: Session,
    sensor_id: UUID,
    version: int,
    *,
    days: Optional[int] = None,
    min_samples: int = MIN_SAMPLES,
) -> dict[str, Any]:
    """Learn every baseline this sensor has enough history for, into `version`.

    The version's existing rows are cleared first. Updating in place would
    leave behind a row for a feature that used to qualify and no longer
    does -- the window moved on, the samples at the current acquisition
    shape fell below the floor -- and a stale row is worse than a missing
    one, because a reader cannot tell it is stale.

    Says nothing about which version is in force. `roll_baseline` and
    `reset_baseline` are where that is decided.
    """
    history = load_history(db, sensor_id, days=days)
    if not history:
        return {"sensor_id": str(sensor_id), "version": version,
                "stored": 0, "refused": 0, "captures_in_window": 0,
                "refused_features": [],
                "reason": "no feature history for this sensor"}

    db.execute(text(f"DELETE FROM {TABLE} "
                    f"WHERE sensor_id = :s AND baseline_version = :v"),
               {"s": str(sensor_id), "v": version})

    stored = refused = 0
    mode_stored = 0
    refusals: dict[str, int] = {}
    for (channel, code), observations in sorted(history.items()):
        # The all-conditions baseline, built from everything usable. It keeps
        # `mode_id` null, which is what a null there has always meant, and it
        # is the fallback for a capture whose mode is unknown -- which is
        # every capture on a machine nobody has configured modes for.
        stats = build_baseline(str(sensor_id), channel, code, observations,
                               min_samples=min_samples)
        if store(db, stats, version):
            stored += 1
        else:
            refused += 1
            refusals[code] = refusals.get(code, 0) + 1

        # And one per mode that has enough history of its own (VIK-040).
        # Additive: a mode-specific normal is offered where it can be built
        # and the all-conditions one still exists where it cannot, so this
        # can never leave a feature with less than it had before.
        by_mode: dict[str, list] = {}
        for observation in observations:
            if observation.mode_id:
                by_mode.setdefault(observation.mode_id, []).append(observation)
        for mode_id, scoped in by_mode.items():
            # An optimisation, not a guard: `build_baseline` refuses below
            # the floor on its own and `store` declines a refusal, so
            # removing this changes nothing but the work done. Said plainly
            # because a line that looks like a safety check and is not one
            # is how the next person comes to rely on it.
            if len(scoped) < min_samples:
                continue
            mode_stats = build_baseline(str(sensor_id), channel, code, scoped,
                                        min_samples=min_samples)
            if store(db, mode_stats, version, mode_id=mode_id):
                mode_stored += 1

    logger.info("Baselines for sensor %s v%d: %d stored, %d refused",
                sensor_id, version, stored, refused)
    return {
        "sensor_id": str(sensor_id), "version": version,
        "stored": stored, "refused": refused,
        "mode_scoped": mode_stored,
        "captures_in_window": max((len(o) for o in history.values()), default=0),
        "refused_features": sorted(refusals),
    }


def roll_baseline(db: Session, sensor_id: UUID, *,
                  days: Optional[int] = None,
                  min_samples: int = MIN_SAMPLES) -> dict[str, Any]:
    """Recompute the baseline in force from the current window.

    The routine update. Refuses on a frozen baseline, and the refusal is the
    feature rather than the failure: a normal that keeps learning from a
    machine that is slowly degrading follows it down, and the degradation
    never becomes anomalous.
    """
    record = lifecycle.require_rollable(db, sensor_id)
    result = compute_into_version(db, sensor_id, record["version"],
                                  days=days, min_samples=min_samples)
    result["state"] = record["state"]
    return result


def reset_baseline(db: Session, sensor_id: UUID, *,
                   reason: Optional[str] = None,
                   created_by: Optional[str] = None,
                   days: Optional[int] = None,
                   min_samples: int = MIN_SAMPLES,
                   activate: bool = True) -> dict[str, Any]:
    """Start a new version, learn it, and put it in force.

    Never edits the version it replaces. That is the whole point of VIK-026:
    a finding recorded three months ago was judged against a particular
    normal, and the only way it stays explainable is for that normal to
    still exist, unchanged, with the finding pointing at it.

    `activate=False` builds it and leaves it in `building`, for a caller
    that wants to look at what was learned before anything is judged
    against it.
    """
    started = lifecycle.start(db, sensor_id, reason=reason,
                              created_by=created_by)
    version = started["version"]
    result = compute_into_version(db, sensor_id, version,
                                  days=days, min_samples=min_samples)

    if activate and result["stored"]:
        record = lifecycle.activate(db, sensor_id, version)
    else:
        record = started
        if activate:
            # Activating a version with nothing in it would retire a working
            # baseline in favour of an empty one, and leave the sensor with
            # no learned normal at all. Refusing to promote it is the safe
            # half; the version stays as a record that the attempt was made.
            result["reason"] = (
                "No baseline could be learned from this sensor's history, so "
                "v%d was left unactivated and the previous baseline stays in "
                "force." % version)
            logger.warning("Baseline v%d for sensor %s stored nothing; "
                           "not activating", version, sensor_id)

    result["state"] = record["state"]
    result["previous_version"] = (started["version"] - 1
                                  if started["version"] > 1 else None)
    return result


def load_baseline_map(db: Session, sensor_id: UUID,
                      version: Optional[int] = None,
                      mode_id: Optional[str] = None) -> dict[tuple[int, str], dict]:
    """The baselines in force, keyed the way a feature row is.

    `mode_id` selects the normal for the operating mode a capture was taken
    in. Where one exists it wins; where it does not, the all-conditions
    baseline is returned instead, so a feature never loses its normal just
    because that mode has too little history yet.

    An explicit `version` reads that one whatever its state, which is how a
    finding recorded against a retired baseline is explained later. With no
    version it reads the one in force -- and returns nothing at all when
    there is none, rather than falling back to the newest rows lying about.
    """
    if version is None:
        record = lifecycle.in_force(db, sensor_id)
        if record is None:
            return {}
        version = record["version"]

    rows = db.execute(text(f"""
        SELECT channel, feature_code, mode_id, median, mad, robust_sigma,
               p05, p50, p95, ewma, sample_count, baseline_version,
               acquisition_sample_rate_hz, acquisition_sample_count,
               confidence, excluded_count, distinct_count, mixed_population,
               other_shape_count, acquisition_step_g, other_step_count
          FROM {TABLE}
         WHERE sensor_id = :s AND baseline_version = :v
           AND (mode_id IS NULL OR mode_id = :mode)
    """), {"s": str(sensor_id), "v": version,
           "mode": str(mode_id) if mode_id else None}).mappings().fetchall()

    # A mode-specific normal beats the all-conditions one for the same
    # feature. That is the point of VIK-040: a machine at two loads has two
    # normals, and the average of them describes neither.
    chosen: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (row["channel"], row["feature_code"])
        if key not in chosen or row["mode_id"] is not None:
            chosen[key] = dict(row)
    return chosen
