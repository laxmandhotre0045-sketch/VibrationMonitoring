"""Feature threshold rule administration.

Until now the limits that decide Normal / Warning / Critical were reachable only
by editing the database: the Settings screen wrote its thresholds to the
browser's localStorage, so what an engineer typed there and what actually judged
their machines were two unrelated sets of numbers. These endpoints are the
missing half.

Reads are open to any signed-in user because the analysis screens want to show a
reading next to the limit that judged it. Writes are administrator-only — a
threshold change silently reclassifies every future measurement on the site.

Scope: a rule with `channel` set applies to that channel alone; a rule with
`channel` null applies to every channel without one of its own. Editing a global
rule therefore moves the limit everywhere it has not been overridden, which is
usually what a site-wide policy change means.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.crud import feature as feature_crud
from app.database import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.models.equipment import Equipment
from app.models.measurement import FeatureThresholdRule
from app.models.sensor import SensorConfiguration
from app.models.user import User
from app.schemas.threshold import (
    ThresholdRuleBulkUpdate,
    ThresholdRuleCreate,
    ThresholdRuleListOut,
    ThresholdRuleOut,
    ThresholdRuleUpdate,
    ThresholdScopeSensorOut,
)
from app.services.threshold_defaults import (
    RULE_TYPE_INFO,
    THRESHOLD_RULE_DEFAULTS,
    default_for,
)

router = APIRouter(prefix="/api/v1/thresholds", tags=["Thresholds"])


# The evaluator's normal_max is the first limit a value crosses, and warning_max
# the second. Every screen names those two differently; these are the labels the
# health table already uses, so the API hands them out rather than letting each
# client guess.
LIMIT_LABELS = {
    "normal_max": "Caution limit",
    "warning_max": "Warning limit",
    "normal_min": "Caution minimum",
    "warning_min": "Warning minimum",
}


def _as_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _matches_default(rule: FeatureThresholdRule) -> bool:
    fallback = default_for(rule.feature_code)
    if fallback is None:
        return False
    return (
        rule.rule_type == fallback.rule_type
        and _as_float(rule.normal_max) == fallback.normal_max
        and _as_float(rule.warning_max) == fallback.warning_max
        and _as_float(rule.normal_min) == fallback.normal_min
        and _as_float(rule.warning_min) == fallback.warning_min
    )


def _rule_out(rule: FeatureThresholdRule, definitions: dict) -> ThresholdRuleOut:
    definition = definitions.get(rule.feature_code)
    info = RULE_TYPE_INFO.get(rule.rule_type, {})
    used = info.get("uses", ["normal_max", "warning_max"])

    return ThresholdRuleOut(
        id=rule.id,
        feature_code=rule.feature_code,
        feature_name=definition.name if definition else None,
        unit=definition.unit if definition else None,
        rule_type=rule.rule_type,
        machine_type=rule.machine_type,
        channel=rule.channel,
        sensor_id=rule.sensor_id,
        equipment_id=rule.equipment_id,
        normal_max=_as_float(rule.normal_max),
        warning_max=_as_float(rule.warning_max),
        normal_min=_as_float(rule.normal_min),
        warning_min=_as_float(rule.warning_min),
        metadata=rule.metadata_ or {},
        is_active=rule.is_active,
        updated_at=rule.updated_at,
        updated_by=rule.updated_by,
        is_default=_matches_default(rule),
        limit_labels={key: LIMIT_LABELS[key] for key in used if key in LIMIT_LABELS},
    )


def _stamp(rule: FeatureThresholdRule, user: User) -> None:
    rule.updated_at = datetime.now(timezone.utc)
    rule.updated_by = user.id


def _apply(rule: FeatureThresholdRule, payload: ThresholdRuleUpdate) -> None:
    """Apply only the fields the caller actually sent.

    A PATCH-style merge matters here: the editor sends one row at a time and the
    limit columns are nullable, so treating an absent field as "clear it" would
    quietly wipe the other half of a range rule.
    """
    provided = payload.model_dump(exclude_unset=True)
    for field in ("normal_max", "warning_max", "normal_min", "warning_min", "is_active"):
        if field in provided:
            setattr(rule, field, provided[field])
    if "metadata" in provided and provided["metadata"] is not None:
        rule.metadata_ = provided["metadata"]


def _validate_against_stored(rule: FeatureThresholdRule, payload: ThresholdRuleUpdate) -> None:
    """Re-check ordering against the row's final state.

    The schema validates the payload in isolation, which cannot catch a request
    that lowers warning_max below a normal_max it did not send.
    """
    provided = payload.model_dump(exclude_unset=True)

    def final(field: str) -> Optional[float]:
        if field in provided:
            return provided[field]
        return _as_float(getattr(rule, field))

    n_max, w_max = final("normal_max"), final("warning_max")
    n_min, w_min = final("normal_min"), final("warning_min")

    if n_max is not None and w_max is not None and w_max <= n_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Warning limit ({w_max}) must be greater than caution limit ({n_max}).",
        )
    if n_min is not None and w_min is not None and w_min >= n_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Warning minimum ({w_min}) must be less than caution minimum ({n_min}).",
        )


def _scope_phrase(payload: ThresholdRuleCreate) -> str:
    """How the scope reads in an error message, narrowest part first."""
    parts: list[str] = []
    if payload.sensor_id is not None:
        parts.append("this sensor")
    elif payload.equipment_id is not None:
        parts.append("this machine")
    elif payload.machine_type:
        parts.append(f"machine type {payload.machine_type}")
    parts.append(
        f"channel {payload.channel}" if payload.channel is not None else "all channels"
    )
    return ", ".join(parts)


def _sensor_roster(db: Session) -> list[ThresholdScopeSensorOut]:
    """Every sensor, named the way an engineer would name it.

    Listed in full rather than only where a rule exists: a coverage view built
    from the rules alone could show which sensors have their own limit but
    never which ones fall back, and the second half is the question being
    asked.
    """
    rows = (
        db.query(SensorConfiguration, Equipment)
        .outerjoin(Equipment, Equipment.id == SensorConfiguration.equipment_id)
        .order_by(Equipment.machine_name.asc().nullslast(),
                  SensorConfiguration.mounting_location.asc())
        .all()
    )

    roster: list[ThresholdScopeSensorOut] = []
    for sensor, equipment in rows:
        where = " · ".join(
            part for part in (sensor.mounting_location, sensor.orientation) if part
        )
        machine = equipment.machine_name if equipment is not None else None
        roster.append(
            ThresholdScopeSensorOut(
                id=sensor.id,
                label=" — ".join(part for part in (machine, where) if part)
                or str(sensor.id),
                machine_name=machine,
                machine_type=equipment.machine_type if equipment is not None else None,
                equipment_id=sensor.equipment_id,
            )
        )
    return roster


@router.get("/rules", response_model=ThresholdRuleListOut)
def list_threshold_rules(
    machine_type: Optional[str] = Query(default=None),
    channel: Optional[int] = Query(default=None, ge=0, le=63),
    sensor_id: Optional[UUID] = Query(default=None),
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ThresholdRuleListOut:
    rules = feature_crud.get_threshold_rules(
        db,
        machine_type=machine_type,
        channel=channel,
        sensor_id=sensor_id,
        include_inactive=include_inactive,
    )
    definitions = feature_crud.get_definition_map(db)
    channels = sorted({r.channel for r in rules if r.channel is not None})

    return ThresholdRuleListOut(
        items=[_rule_out(rule, definitions) for rule in rules],
        rule_types=RULE_TYPE_INFO,
        overridden_channels=channels,
        sensors=_sensor_roster(db),
    )


@router.get("/defaults", response_model=dict)
def get_threshold_defaults(_: User = Depends(get_current_user)) -> dict:
    """Factory limits, for showing what a reset would restore."""
    return {
        "rule_types": RULE_TYPE_INFO,
        "limit_labels": LIMIT_LABELS,
        "defaults": {
            code: {
                "rule_type": value.rule_type,
                "normal_max": value.normal_max,
                "warning_max": value.warning_max,
                "normal_min": value.normal_min,
                "warning_min": value.warning_min,
                "metadata": value.metadata,
            }
            for code, value in THRESHOLD_RULE_DEFAULTS.items()
        },
    }


@router.get("/rules/{rule_id}", response_model=ThresholdRuleOut)
def get_threshold_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ThresholdRuleOut:
    rule = feature_crud.get_threshold_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")
    return _rule_out(rule, feature_crud.get_definition_map(db))


@router.post("/rules", response_model=ThresholdRuleOut, status_code=status.HTTP_201_CREATED)
def create_threshold_rule(
    payload: ThresholdRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ThresholdRuleOut:
    definitions = feature_crud.get_definition_map(db)
    if payload.feature_code not in definitions:
        raise HTTPException(
            status_code=422, detail=f"Unknown feature code '{payload.feature_code}'"
        )

    # A scope must name something that exists, or the rule is written for a
    # machine nobody can find and silently never fires.
    if payload.sensor_id is not None:
        if crud.get_sensor_by_id(db, payload.sensor_id) is None:
            raise HTTPException(status_code=422, detail="Unknown sensor_id.")
    if payload.equipment_id is not None:
        if crud.get_equipment_by_id(db, payload.equipment_id) is None:
            raise HTTPException(status_code=422, detail="Unknown equipment_id.")

    existing = feature_crud.find_threshold_rule(
        db,
        payload.feature_code,
        channel=payload.channel,
        machine_type=payload.machine_type,
        sensor_id=payload.sensor_id,
        equipment_id=payload.equipment_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A rule for {payload.feature_code} at this scope "
                f"({_scope_phrase(payload)}) already exists; update it instead."
            ),
        )

    # An override inherits the global rule's type and any limits it did not
    # restate, so overriding one number does not require retyping the rest.
    fallback = default_for(payload.feature_code)
    rule_type = payload.rule_type or (fallback.rule_type if fallback else None)
    if rule_type is None:
        raise HTTPException(
            status_code=422,
            detail=f"No default rule type for '{payload.feature_code}'; supply rule_type.",
        )

    provided = payload.model_dump(exclude_unset=True)

    def limit(field: str):
        if field in provided:
            return provided[field]
        return getattr(fallback, field) if fallback else None

    rule = FeatureThresholdRule(
        id=uuid4(),
        feature_code=payload.feature_code,
        rule_type=rule_type,
        machine_type=payload.machine_type,
        channel=payload.channel,
        sensor_id=payload.sensor_id,
        equipment_id=payload.equipment_id,
        normal_max=limit("normal_max"),
        warning_max=limit("warning_max"),
        normal_min=limit("normal_min"),
        warning_min=limit("warning_min"),
        metadata_=payload.metadata
        if payload.metadata is not None
        else (dict(fallback.metadata) if fallback else {}),
        is_active=payload.is_active,
    )
    _stamp(rule, current_user)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule, definitions)


@router.put("/rules", response_model=ThresholdRuleListOut)
def bulk_update_threshold_rules(
    payload: ThresholdRuleBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ThresholdRuleListOut:
    """Save a whole editor screen at once.

    All or nothing: the editor shows one Save for the table, so a row failing
    validation must not leave the other rows applied and the screen half-saved.
    """
    if not payload.items:
        raise HTTPException(status_code=422, detail="No rules supplied")

    by_id = {rule.id: rule for rule in feature_crud.get_threshold_rules(db)}
    missing = [str(item.id) for item in payload.items if item.id not in by_id]
    if missing:
        joined = ", ".join(missing)
        raise HTTPException(status_code=404, detail=f"Unknown threshold rule(s): {joined}")

    for item in payload.items:
        _validate_against_stored(by_id[item.id], item)

    for item in payload.items:
        rule = by_id[item.id]
        _apply(rule, item)
        _stamp(rule, current_user)

    db.commit()

    definitions = feature_crud.get_definition_map(db)
    rules = feature_crud.get_threshold_rules(db)
    return ThresholdRuleListOut(
        items=[_rule_out(rule, definitions) for rule in rules],
        rule_types=RULE_TYPE_INFO,
        overridden_channels=sorted({r.channel for r in rules if r.channel is not None}),
    )


@router.put("/rules/{rule_id}", response_model=ThresholdRuleOut)
def update_threshold_rule(
    rule_id: UUID,
    payload: ThresholdRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ThresholdRuleOut:
    rule = feature_crud.get_threshold_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")

    _validate_against_stored(rule, payload)
    _apply(rule, payload)
    _stamp(rule, current_user)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule, feature_crud.get_definition_map(db))


@router.post("/rules/{rule_id}/reset", response_model=ThresholdRuleOut)
def reset_threshold_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ThresholdRuleOut:
    """Restore a rule's factory limits."""
    rule = feature_crud.get_threshold_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")

    fallback = default_for(rule.feature_code)
    if fallback is None:
        raise HTTPException(
            status_code=422,
            detail=f"No factory default is defined for '{rule.feature_code}'.",
        )

    rule.rule_type = fallback.rule_type
    rule.normal_max = fallback.normal_max
    rule.warning_max = fallback.warning_max
    rule.normal_min = fallback.normal_min
    rule.warning_min = fallback.warning_min
    rule.metadata_ = dict(fallback.metadata)
    rule.is_active = True
    _stamp(rule, current_user)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule, feature_crud.get_definition_map(db))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_threshold_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    """Drop an override so its scope follows the broader rule again.

    Global rules are not deletable: removing one would leave its feature with no
    limits at all, which reads as "healthy" rather than "unmonitored". Reset it
    or deactivate it instead.

    "Global" is decided on every scope column, not on channel and machine type
    alone. A rule written for one sensor also has both of those null, so the
    narrower test refused to delete it — the one scope a limit could be created
    at but never removed from.
    """
    rule = feature_crud.get_threshold_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")
    if (
        rule.channel is None
        and rule.machine_type is None
        and rule.sensor_id is None
        and rule.equipment_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Global rules cannot be deleted. Reset it to defaults, or set is_active=false to stop evaluating it.",
        )

    db.delete(rule)
    db.commit()
