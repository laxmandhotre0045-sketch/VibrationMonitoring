"""When a learned normal starts, stops moving, and is replaced — VIK-026.

VIK-025 works out what normal looks like. This decides which normal is in
force, and it is a separate question: the statistics can be perfect and
still be the wrong ones to judge today's capture against.

**Four states, because the ticket names four things.**

``building``    Assembled but not in force. Nothing is judged against it.
``active``      In force, and still rolling as captures arrive.
``frozen``      In force, and deliberately no longer rolling.
``superseded``  Replaced. Kept, because a finding recorded against it has to
                stay explainable -- that is the whole reason versions exist.

**Freeze is the one that earns the table.** A rolling baseline learns from
whatever arrives. A machine that degrades over months produces captures that
worsen gradually, the baseline follows them down, and every capture stays
within a sigma of a normal that is itself sliding. The fault never becomes
anomalous, because "normal" moved with it. Freezing pins the normal to a
period somebody is willing to vouch for, and that is the only way a slow
degradation shows up as one.

**At most one version is in force.** Enforced by a partial unique index
rather than by this module being careful, because two active baselines is
not a richer answer -- it is an ambiguity that every reader downstream would
resolve differently.

This module does not compute statistics and does not import the engine that
does. It owns the state and nothing else; `baseline_engine.roll_baseline`
and `reset_baseline` are where the two meet.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TABLE = "baseline_versions"

BUILDING = "building"
ACTIVE = "active"
FROZEN = "frozen"
SUPERSEDED = "superseded"

#: The states in which a version is the one findings are judged against.
#: Frozen counts: it has stopped learning, not stopped applying.
IN_FORCE = (ACTIVE, FROZEN)

#: Interpolated into SQL rather than bound, because these are module
#: constants and never reach here from a request. The same tuple also spells
#: the partial unique index in migration 028, and the two must agree.
_IN_FORCE_SQL = "(" + ", ".join(f"'{s}'" for s in IN_FORCE) + ")"

COLUMNS = ("id, sensor_id, version, state, reason, created_by, created_at, "
           "activated_at, frozen_at, superseded_at, superseded_by")


class LifecycleError(ValueError):
    """A transition that is not allowed from the current state.

    A ValueError rather than an HTTP error: the rule is about the baseline,
    not about the request, and the same rule has to hold when a script or a
    scheduled job asks.
    """


def _row(result) -> Optional[dict[str, Any]]:
    row = result.mappings().fetchone()
    return dict(row) if row else None


def get_version(db: Session, sensor_id: UUID, version: int) -> Optional[dict]:
    return _row(db.execute(text(
        f"SELECT {COLUMNS} FROM {TABLE} WHERE sensor_id = :s AND version = :v"),
        {"s": str(sensor_id), "v": int(version)}))


def in_force(db: Session, sensor_id: UUID) -> Optional[dict]:
    """The version today's captures are judged against, or None.

    None is a real answer and callers must handle it: a sensor with no
    baseline in force has no learned normal, and inventing one from the
    newest rows lying around would be exactly the mistake versions exist to
    prevent.
    """
    return _row(db.execute(text(
        f"SELECT {COLUMNS} FROM {TABLE} "
        f"WHERE sensor_id = :s AND state IN {_IN_FORCE_SQL}"),
        {"s": str(sensor_id)}))


def history(db: Session, sensor_id: UUID) -> list[dict]:
    """Every version this sensor has had, newest first."""
    return [dict(r) for r in db.execute(text(
        f"SELECT {COLUMNS} FROM {TABLE} WHERE sensor_id = :s "
        f"ORDER BY version DESC"), {"s": str(sensor_id)}).mappings().fetchall()]


def next_version(db: Session, sensor_id: UUID) -> int:
    current = db.execute(text(
        f"SELECT COALESCE(MAX(version), 0) FROM {TABLE} WHERE sensor_id = :s"),
        {"s": str(sensor_id)}).scalar()
    return int(current or 0) + 1


def start(db: Session, sensor_id: UUID, *, reason: Optional[str] = None,
          created_by: Optional[str] = None) -> dict:
    """Open a new version, not yet in force.

    Deliberately two steps. A version is built before it is trusted, and the
    gap between the two is where somebody can look at what was learned
    before it starts judging anything. `reset_baseline` closes the gap for
    callers that do not want it.
    """
    version = next_version(db, sensor_id)
    db.execute(text(f"""
        INSERT INTO {TABLE} (sensor_id, version, state, reason, created_by)
        VALUES (:s, :v, '{BUILDING}', :reason, :by)
    """), {"s": str(sensor_id), "v": version, "reason": reason,
           "by": created_by})
    logger.info("Baseline v%d started for sensor %s: %s",
                version, sensor_id, reason or "no reason given")
    return get_version(db, sensor_id, version)


def activate(db: Session, sensor_id: UUID, version: int) -> dict:
    """Put a built version in force, retiring whatever held that place.

    The old version is superseded first and the new one promoted second.
    That order is not cosmetic: the database permits one version in force
    per sensor, so promoting first would collide with the row being
    replaced.
    """
    record = get_version(db, sensor_id, version)
    if record is None:
        raise LifecycleError(
            f"Sensor {sensor_id} has no baseline version {version} to activate.")
    if record["state"] == SUPERSEDED:
        raise LifecycleError(
            f"Baseline v{version} was superseded on "
            f"{record['superseded_at']:%Y-%m-%d} by v{record['superseded_by']}. "
            f"A retired version cannot be brought back, because findings "
            f"recorded since were judged against its replacement. Start a new "
            f"version instead.")
    if record["state"] in IN_FORCE:
        return record

    previous = in_force(db, sensor_id)
    if previous is not None:
        db.execute(text(f"""
            UPDATE {TABLE} SET state = '{SUPERSEDED}', superseded_at = now(),
                               superseded_by = :new
             WHERE sensor_id = :s AND version = :old
        """), {"s": str(sensor_id), "old": previous["version"], "new": version})

    db.execute(text(f"""
        UPDATE {TABLE} SET state = '{ACTIVE}', activated_at = now()
         WHERE sensor_id = :s AND version = :v
    """), {"s": str(sensor_id), "v": version})

    logger.info("Baseline v%d activated for sensor %s%s", version, sensor_id,
                f", superseding v{previous['version']}" if previous else "")
    return get_version(db, sensor_id, version)


def freeze(db: Session, sensor_id: UUID, *, reason: Optional[str] = None) -> dict:
    """Stop the baseline in force from learning, without retiring it.

    The reason is appended rather than replacing the one the version was
    started with: why a normal was learned and why it was later pinned are
    different facts, and overwriting the first loses it.
    """
    record = in_force(db, sensor_id)
    if record is None:
        raise LifecycleError(
            f"Sensor {sensor_id} has no baseline in force, so there is "
            f"nothing to freeze.")
    if record["state"] == FROZEN:
        return record

    note = (f"{record['reason']}\nFrozen: {reason}" if reason and record["reason"]
            else (f"Frozen: {reason}" if reason else record["reason"]))
    db.execute(text(f"""
        UPDATE {TABLE} SET state = '{FROZEN}', frozen_at = now(), reason = :r
         WHERE sensor_id = :s AND version = :v
    """), {"s": str(sensor_id), "v": record["version"], "r": note})
    logger.info("Baseline v%d frozen for sensor %s: %s",
                record["version"], sensor_id, reason or "no reason given")
    return get_version(db, sensor_id, record["version"])


def thaw(db: Session, sensor_id: UUID) -> dict:
    """Let the baseline in force roll again.

    `frozen_at` is cleared, so a version that was frozen and released does
    not read as still pinned. The fact that it happened survives in the
    reason text, which is where a human note belongs.
    """
    record = in_force(db, sensor_id)
    if record is None:
        raise LifecycleError(
            f"Sensor {sensor_id} has no baseline in force, so there is "
            f"nothing to thaw.")
    if record["state"] == ACTIVE:
        return record

    db.execute(text(f"""
        UPDATE {TABLE} SET state = '{ACTIVE}', frozen_at = NULL
         WHERE sensor_id = :s AND version = :v
    """), {"s": str(sensor_id), "v": record["version"]})
    logger.info("Baseline v%d thawed for sensor %s", record["version"], sensor_id)
    return get_version(db, sensor_id, record["version"])


def require_rollable(db: Session, sensor_id: UUID) -> dict:
    """The version a roll may recompute, or a refusal saying why not.

    Split out so that the engine's roll and any future scheduled roll ask
    the same question and get the same answer. A frozen baseline refusing to
    roll is the point of freezing, so the refusal explains itself rather
    than reading as a failure.
    """
    record = in_force(db, sensor_id)
    if record is None:
        raise LifecycleError(
            f"Sensor {sensor_id} has no baseline in force. Start one and "
            f"activate it before rolling.")
    if record["state"] == FROZEN:
        raise LifecycleError(
            f"Baseline v{record['version']} was frozen on "
            f"{record['frozen_at']:%Y-%m-%d} and does not roll. That is what "
            f"freezing is for: a normal that keeps learning from a machine "
            f"that is slowly degrading follows it down, and the degradation "
            f"never becomes anomalous. Thaw it deliberately, or start a new "
            f"version.")
    return record
