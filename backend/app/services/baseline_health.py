"""How much the learned normal is worth — VIK-027.

Everything downstream compares a capture against a baseline and reports how
unusual it is. That number inherits the baseline's weaknesses silently: a
normal learned from thirteen captures, or from a window that ended four
months ago, or from a machine that was already faulty, produces a confident
z-score that means very little. Nothing in the answer says so.

This is where it says so. Availability, confidence, freshness and sample
count, per the ticket -- and coverage, because "the baseline is available"
is misleading when it holds twelve features out of forty-six.

The honest answer for this platform today is not a good one, and that is the
point. The roadmap records what the old arrangement cost: the only baseline
was a copy of the very file being compared against it, and 144 readings
would have turned green the moment somebody nominated it. A read model that
cannot express "available, and worth almost nothing" would let that happen
again.

Everything here is read from stored columns. Recomputing a baseline to
answer a question about it would mean rebuilding from history on every
request, and would report on a baseline that is not the one in force.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import numpy as np

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.baseline import MIN_SAMPLES, PREFERRED_SAMPLES
from app.services import baseline_lifecycle as lifecycle

logger = logging.getLogger(__name__)

TABLE = "feature_baseline_stats"

#: At or below this, a baseline is reported as low confidence whatever else
#: is true of it. At, not below: the engine halves confidence for a mixed
#: population, which lands exactly here, and a threshold that excluded its
#: own motivating case would flag nothing on this platform's real data.
LOW_CONFIDENCE = 0.5

#: A window that ended this long ago describes a period that is over.
#: Deliberately generous: the requirement asks for two to four weeks of
#: running data, so a month-old window is still describing roughly the
#: machine, and anything older is describing its past.
STALE_AFTER_DAYS = 30.0


def _age_days(when: Optional[datetime]) -> Optional[float]:
    if when is None:
        return None
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return round((now - when).total_seconds() / 86400.0, 2)


def _summarise(values: list[float]) -> dict[str, Optional[float]]:
    if not values:
        return {"min": None, "median": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {"min": float(array.min()),
            "median": float(np.median(array)),
            "max": float(array.max())}


def sensor_health(db: Session, sensor_id: UUID,
                  expected_feature_count: Optional[int] = None) -> dict[str, Any]:
    """What the baseline in force for this sensor is worth.

    `available` is False when there is no version in force or it holds no
    rows, and `reason` then says which -- those are different situations and
    a caller that treats them alike will tell somebody to wait for more data
    when the real problem is that nobody ever activated a baseline.
    """
    version = lifecycle.in_force(db, sensor_id)
    if version is None:
        return _unavailable(
            sensor_id,
            "No baseline is in force for this sensor. Either none has been "
            "built, or one was built and never activated -- a version in "
            "`building` is deliberately not used for comparison.",
            history=lifecycle.history(db, sensor_id))

    rows = db.execute(text(f"""
        SELECT channel, feature_code, sample_count, confidence,
               mixed_population, excluded_count, distinct_count,
               other_shape_count, window_start, window_end,
               acquisition_sample_rate_hz, acquisition_sample_count
          FROM {TABLE}
         WHERE sensor_id = :s AND baseline_version = :v
    """), {"s": str(sensor_id), "v": version["version"]}).mappings().fetchall()

    if not rows:
        return _unavailable(
            sensor_id,
            f"Baseline v{version['version']} is in force but holds no "
            f"features. Nothing has enough history at a single acquisition "
            f"shape to learn from.",
            version=version, history=lifecycle.history(db, sensor_id))

    confidences = [float(r["confidence"]) for r in rows
                   if r["confidence"] is not None]
    samples = [int(r["sample_count"]) for r in rows]
    channels = sorted({int(r["channel"]) for r in rows})
    codes = {r["feature_code"] for r in rows}
    window_end = max(r["window_end"] for r in rows)
    window_start = min(r["window_start"] for r in rows)

    captures_since = int(db.execute(text("""
        SELECT COUNT(*) FROM sensor_data_uploads
         WHERE sensor_id = :s AND created_at > :t
    """), {"s": str(sensor_id), "t": window_end}).scalar() or 0)

    expected = (expected_feature_count * len(channels)
                if expected_feature_count and channels else None)

    mixed = sum(1 for r in rows if r["mixed_population"])
    thin = sum(1 for s in samples if s < PREFERRED_SAMPLES)
    weak = sum(1 for c in confidences if c <= LOW_CONFIDENCE)
    other_shape = sum(int(r["other_shape_count"] or 0) for r in rows)
    excluded = sum(int(r["excluded_count"] or 0) for r in rows)

    age = _age_days(window_end)
    stale = bool(age is not None and age > STALE_AFTER_DAYS)
    # A window the sensor has since outgrown. Counted as well as timed,
    # because a busy sensor can leave a baseline behind in a week and a
    # quiet one can keep a three-month window perfectly current.
    #
    # Against the median rather than the largest: one feature with a long
    # history should not suppress the flag for the forty-five that were
    # built from far fewer.
    typical_samples = float(np.median(samples))
    outgrown = bool(captures_since > typical_samples)

    health = {
        "sensor_id": str(sensor_id),
        "available": True,
        "reason": None,
        "version": _version_out(version),
        "coverage": {
            "rows": len(rows),
            "channels": channels,
            "distinct_features": len(codes),
            "expected_rows": expected,
            "fraction": (round(len(rows) / expected, 3)
                         if expected else None),
        },
        "confidence": {
            **_summarise(confidences),
            "low_confidence_rows": weak,
            "threshold": LOW_CONFIDENCE,
        },
        "samples": {
            **_summarise([float(s) for s in samples]),
            "minimum_required": MIN_SAMPLES,
            "preferred": PREFERRED_SAMPLES,
            "below_preferred_rows": thin,
        },
        "freshness": {
            "window_start": window_start,
            "window_end": window_end,
            "age_days": age,
            "captures_since_window": captures_since,
            "stale": stale,
            "outgrown": outgrown,
            "stale_after_days": STALE_AFTER_DAYS,
        },
        "exclusions": {
            "quality_excluded_observations": excluded,
            "other_shape_observations": other_shape,
            "mixed_population_rows": mixed,
        },
        "warnings": [],
        "history": [_version_out(v) for v in lifecycle.history(db, sensor_id)],
    }
    health["warnings"] = _warnings(health, rows)
    return health


def _warnings(health: dict, rows) -> list[str]:
    """Plain sentences a reader can act on, not flags they must interpret.

    Ordered by how much they undermine the baseline, because a caller that
    shows only the first one should show the worst one.
    """
    out: list[str] = []
    samples, confidence = health["samples"], health["confidence"]
    freshness, exclusions = health["freshness"], health["exclusions"]
    coverage = health["coverage"]

    if samples["median"] is not None and samples["median"] < PREFERRED_SAMPLES:
        out.append(
            f"Learned from {samples['median']:.0f} captures at the median, "
            f"against the {PREFERRED_SAMPLES} at which a spread expressed in "
            f"sigma means what it says. Thresholds built on this will move as "
            f"more data arrives.")

    if exclusions["mixed_population_rows"]:
        out.append(
            f"{exclusions['mixed_population_rows']} feature(s) were learned "
            f"from a window holding more than one population. Their median "
            f"and spread are usable; their 5th and 95th percentiles describe "
            f"the other population and should not be read as limits.")

    if freshness["stale"]:
        out.append(
            f"The window ended {freshness['age_days']:.0f} days ago. This "
            f"describes the machine as it was, and a comparison against it "
            f"measures the gap between then and now as well as any fault.")

    if freshness["outgrown"]:
        out.append(
            f"{freshness['captures_since_window']} capture(s) have arrived "
            f"since the window closed, more than the baseline was built "
            f"from. Rolling it would fold them in.")

    if confidence["low_confidence_rows"]:
        out.append(
            f"{confidence['low_confidence_rows']} feature(s) scored at or "
            f"below {LOW_CONFIDENCE} confidence. A finding that rests on one "
            f"of them rests on very little.")

    if exclusions["quality_excluded_observations"]:
        out.append(
            f"{exclusions['quality_excluded_observations']} observation(s) "
            f"were kept out because the quality engine called the capture "
            f"invalid.")

    if exclusions["other_shape_observations"]:
        out.append(
            f"{exclusions['other_shape_observations']} observation(s) were "
            f"kept out because they were taken at a different sample rate or "
            f"record length. Half the features move by a quarter or more when "
            f"that changes, so mixing them would find every capture anomalous.")

    if coverage["fraction"] is not None and coverage["fraction"] < 1.0:
        out.append(
            f"{coverage['rows']} of {coverage['expected_rows']} "
            f"channel-feature pairs have a baseline. The rest have no learned "
            f"normal, and a comparison against them is not available rather "
            f"than normal.")

    if health["version"]["state"] == lifecycle.FROZEN:
        out.append(
            "This baseline is frozen and no longer learning. That is "
            "deliberate, but it means a genuine change in how the machine "
            "runs will keep reading as anomalous until it is thawed or "
            "replaced.")

    return out


def _version_out(record: dict) -> dict[str, Any]:
    return {
        "version": record["version"],
        "state": record["state"],
        "reason": record["reason"],
        "created_by": record["created_by"],
        "created_at": record["created_at"],
        "activated_at": record["activated_at"],
        "frozen_at": record["frozen_at"],
        "superseded_at": record["superseded_at"],
        "superseded_by": record["superseded_by"],
        "age_days": _age_days(record["activated_at"] or record["created_at"]),
    }


def _unavailable(sensor_id: UUID, reason: str, *,
                 version: Optional[dict] = None,
                 history: Optional[list[dict]] = None) -> dict[str, Any]:
    """The shape of an answer that has no baseline in it.

    Same keys as a healthy one, with nulls. A caller must not have to branch
    on the shape of the response to find out whether there is a baseline --
    it reads `available`, and everything else is there either way.
    """
    return {
        "sensor_id": str(sensor_id),
        "available": False,
        "reason": reason,
        "version": _version_out(version) if version else None,
        "coverage": {"rows": 0, "channels": [], "distinct_features": 0,
                     "expected_rows": None, "fraction": None},
        "confidence": {"min": None, "median": None, "max": None,
                       "low_confidence_rows": 0, "threshold": LOW_CONFIDENCE},
        "samples": {"min": None, "median": None, "max": None,
                    "minimum_required": MIN_SAMPLES,
                    "preferred": PREFERRED_SAMPLES,
                    "below_preferred_rows": 0},
        "freshness": {"window_start": None, "window_end": None,
                      "age_days": None, "captures_since_window": 0,
                      "stale": False, "outgrown": False,
                      "stale_after_days": STALE_AFTER_DAYS},
        "exclusions": {"quality_excluded_observations": 0,
                       "other_shape_observations": 0,
                       "mixed_population_rows": 0},
        "warnings": [reason],
        "history": [_version_out(v) for v in (history or [])],
    }


def feature_health(db: Session, sensor_id: UUID, channel: int,
                   feature_code: str) -> dict[str, Any]:
    """The same question about one feature on one channel.

    What a finding needs to defend itself: this exact baseline, its sample
    count, its confidence, and whether its percentiles can be trusted.
    """
    version = lifecycle.in_force(db, sensor_id)
    if version is None:
        return {"available": False, "reason": "No baseline is in force."}

    row = db.execute(text(f"""
        SELECT * FROM {TABLE}
         WHERE sensor_id = :s AND baseline_version = :v
           AND channel = :c AND feature_code = :f
    """), {"s": str(sensor_id), "v": version["version"],
           "c": int(channel), "f": feature_code}).mappings().fetchone()

    if row is None:
        return {
            "available": False,
            "version": version["version"],
            "reason": (f"{feature_code} on channel {channel} has no learned "
                       f"normal in baseline v{version['version']}. There was "
                       f"not enough usable history at one acquisition shape "
                       f"to build one, so there is nothing to compare "
                       f"against -- which is not the same as normal."),
        }

    out = dict(row)
    out["available"] = True
    out["reason"] = None
    out["version"] = version["version"]
    out["state"] = version["state"]
    out["age_days"] = _age_days(row["window_end"])
    out["percentiles_trustworthy"] = not bool(row["mixed_population"])
    return out
