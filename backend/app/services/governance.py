"""Reading and keeping the model registry — section 22.

`app.ai.versions` declares what the code is running; this table records
what has ever run, when, on what data, and how well. The pair is what makes
"no model should be changed silently" checkable rather than aspirational.

**Performance is measured from analyst feedback, or reported as unmeasured.**
Section 22 asks for model performance and the only ground truth this
platform has is what analysts said about its findings. Where nobody has
judged anything, the figure is null with a reason -- a model nobody has
checked has no measured performance, which is a different statement from
performing badly, and inventing a number here would be the worst place in
the system to do it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.feedback import NEGATIVE, POSITIVE
from app.ai.versions import COMPONENTS, BY_KEY

logger = logging.getLogger(__name__)

TABLE = "model_versions"
FEEDBACK = "analyst_feedback"

#: Which registered component each stored engine_version belongs to, so
#: performance can be attributed to the thing that produced the finding.
FEEDBACK_COMPONENT = "fault"


def registry(db: Session) -> list[dict[str, Any]]:
    """Every version ever registered, newest first within each component."""
    rows = db.execute(text(f"""
        SELECT component, name, version, stamps, trained_at,
               training_period_start, training_period_end,
               trained_on_captures, performance, notes, effective_from,
               superseded_at, superseded_by
          FROM {TABLE}
         ORDER BY component, effective_from DESC
    """)).mappings().fetchall()
    return [dict(r) for r in rows]


def unregistered(db: Session) -> list[str]:
    """Components whose running version has no row in the registry.

    This is the check behind section 22's closing line. A version the code
    stamps on its output and the registry has never heard of is exactly a
    model that changed silently.
    """
    known = {(r["component"], r["version"]) for r in registry(db)}
    return [f"{c.key} v{c.version}" for c in COMPONENTS
            if (c.key, c.version) not in known]


def model_performance(db: Session,
                      component: str = FEEDBACK_COMPONENT) -> dict[str, Any]:
    """What analysts have said about this component's output.

    Only the fault engine currently produces findings an analyst judges, so
    only it has measurable performance. The others report as unmeasured
    rather than as perfect.
    """
    if component != FEEDBACK_COMPONENT:
        return {
            "measured": False, "judged": 0,
            "reason": (
                f"Nothing this component produces is judged by an analyst, "
                f"so its performance is unmeasured. Only the fault engine "
                f"generates findings that get a verdict."),
        }

    rows = {r[0]: r[1] for r in db.execute(text(f"""
        SELECT verdict, COUNT(*) FROM {FEEDBACK} GROUP BY verdict
    """)).fetchall()}

    confirmed = sum(rows.get(v, 0) for v in POSITIVE)
    rejected = sum(rows.get(v, 0) for v in NEGATIVE)
    judged = confirmed + rejected

    if not judged:
        return {
            "measured": False, "judged": 0, "confirmed": 0, "rejected": 0,
            "precision": None,
            "reason": (
                "No analyst has confirmed or rejected a finding, so this "
                "engine has no measured performance. That is not the same "
                "as performing badly, and a number here would be invented."),
        }

    precision = confirmed / judged
    return {
        "measured": True, "judged": judged, "confirmed": confirmed,
        "rejected": rejected, "precision": round(precision, 3),
        "reason": (
            f"Of {judged} finding(s) an analyst judged, {confirmed} were "
            f"confirmed -- a precision of {precision:.0%}. Measured from "
            f"analyst verdicts, which is the only ground truth this "
            f"platform has."),
    }


def register(
    db: Session, *, component: str, version: str,
    notes: str,
    trained_at: Optional[datetime] = None,
    training_period_start: Optional[datetime] = None,
    training_period_end: Optional[datetime] = None,
    trained_on_captures: Optional[int] = None,
) -> dict[str, Any]:
    """Record a new version, superseding whatever is in force.

    `notes` is required. A version number with no account of what changed
    is a string, and the whole point of section 22 is that somebody reading
    a stored row months later can find out why it differs.
    """
    if component not in BY_KEY:
        raise ValueError(f"{component!r} is not a declared component")
    if not (notes or "").strip():
        raise ValueError(
            "A version needs a note saying what changed. Without one the "
            "registry records that something happened and not what.")

    now = datetime.now(timezone.utc)
    db.execute(text(f"""
        UPDATE {TABLE}
           SET superseded_at = :now, superseded_by = :version
         WHERE component = :c AND superseded_at IS NULL
    """), {"now": now, "version": version, "c": component})

    db.execute(text(f"""
        INSERT INTO {TABLE}
            (component, name, version, stamps, trained_at,
             training_period_start, training_period_end,
             trained_on_captures, notes, effective_from)
        VALUES (:c, :name, :version, :stamps, :trained_at, :start, :end,
                :captures, :notes, :now)
    """), {
        "c": component, "name": BY_KEY[component].name, "version": version,
        "stamps": BY_KEY[component].stamps, "trained_at": trained_at,
        "start": training_period_start, "end": training_period_end,
        "captures": trained_on_captures, "notes": notes.strip(), "now": now})

    return {"component": component, "version": version, "effective_from": now}


def summary(db: Session) -> dict[str, Any]:
    """Section 22 as one answer, including whether it is being honoured."""
    rows = registry(db)
    gaps = unregistered(db)
    in_force = [r for r in rows if r["superseded_at"] is None]

    baselines = db.execute(text("""
        SELECT COUNT(*) FROM baseline_versions
         WHERE state IN ('active', 'frozen')
    """)).scalar() or 0
    feedback_rows = db.execute(text(f"""
        SELECT COUNT(*) FROM {FEEDBACK}
    """)).scalar() or 0

    return {
        "components": [
            {**r, "performance": model_performance(db, r["component"])}
            for r in in_force],
        "history": rows,
        "unregistered": gaps,
        "baselines_in_force": int(baselines),
        "feedback_records": int(feedback_rows),
        "compliant": not gaps,
        "reason": (
            "Every version the code is running is registered with an "
            "account of what it is and what it stamps."
            if not gaps else
            f"{len(gaps)} running version(s) are not in the registry: "
            f"{', '.join(gaps)}. Section 22 requires that no model changes "
            f"silently, and an unregistered version is exactly that."),
    }
