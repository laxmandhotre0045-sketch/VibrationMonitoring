from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.measurement import (
    BaselineChannelFeature,
    FeatureDefinition,
    FeatureThresholdRule,
    MeasurementChannelFeature,
    MeasurementChannelFeatureTrend,
    SensorDataUpload,
)


def get_active_threshold_rules(
    db: Session, machine_type: str | None = None
) -> List[FeatureThresholdRule]:
    query = db.query(FeatureThresholdRule).filter(FeatureThresholdRule.is_active.is_(True))
    if machine_type:
        typed = query.filter(FeatureThresholdRule.machine_type == machine_type).all()
        if typed:
            return typed
    return query.filter(FeatureThresholdRule.machine_type.is_(None)).all()


def get_feature_definitions(db: Session) -> List[FeatureDefinition]:
    return (
        db.query(FeatureDefinition)
        .filter(FeatureDefinition.is_active.is_(True))
        .order_by(FeatureDefinition.sort_order)
        .all()
    )


def get_definition_map(db: Session) -> dict[str, FeatureDefinition]:
    return {d.code: d for d in get_feature_definitions(db)}


def delete_measurement_features(db: Session, upload_id: UUID) -> int:
    count = (
        db.query(MeasurementChannelFeature)
        .filter(MeasurementChannelFeature.upload_id == upload_id)
        .count()
    )
    db.query(MeasurementChannelFeature).filter(
        MeasurementChannelFeature.upload_id == upload_id
    ).delete(synchronize_session=False)
    db.commit()
    return count


def delete_measurement_feature_trends(db: Session, upload_id: UUID) -> int:
    count = (
        db.query(MeasurementChannelFeatureTrend)
        .filter(MeasurementChannelFeatureTrend.upload_id == upload_id)
        .count()
    )
    db.query(MeasurementChannelFeatureTrend).filter(
        MeasurementChannelFeatureTrend.upload_id == upload_id
    ).delete(synchronize_session=False)
    db.commit()
    return count


def get_measurement_features(
    db: Session,
    upload_id: UUID,
    channel: int | None = None,
) -> List[MeasurementChannelFeature]:
    query = db.query(MeasurementChannelFeature).filter(
        MeasurementChannelFeature.upload_id == upload_id
    )
    if channel is not None:
        query = query.filter(MeasurementChannelFeature.channel == channel)
    return query.order_by(
        MeasurementChannelFeature.channel, MeasurementChannelFeature.feature_code
    ).all()


def get_measurement_feature_trends(
    db: Session,
    upload_id: UUID,
    channel: int,
    feature_code: str | None = None,
) -> List[MeasurementChannelFeatureTrend]:
    query = db.query(MeasurementChannelFeatureTrend).filter(
        MeasurementChannelFeatureTrend.upload_id == upload_id,
        MeasurementChannelFeatureTrend.channel == channel,
    )
    if feature_code is not None:
        query = query.filter(MeasurementChannelFeatureTrend.feature_code == feature_code)
    return query.order_by(
        MeasurementChannelFeatureTrend.feature_code,
        MeasurementChannelFeatureTrend.segment_index,
    ).all()


def delete_baseline_features(db: Session, baseline_id: UUID) -> int:
    count = (
        db.query(BaselineChannelFeature)
        .filter(BaselineChannelFeature.baseline_id == baseline_id)
        .count()
    )
    db.query(BaselineChannelFeature).filter(
        BaselineChannelFeature.baseline_id == baseline_id
    ).delete(synchronize_session=False)
    db.commit()
    return count


def get_baseline_features(
    db: Session,
    baseline_id: UUID,
    channel: int | None = None,
) -> List[BaselineChannelFeature]:
    query = db.query(BaselineChannelFeature).filter(
        BaselineChannelFeature.baseline_id == baseline_id
    )
    if channel is not None:
        query = query.filter(BaselineChannelFeature.channel == channel)
    return query.order_by(
        BaselineChannelFeature.channel, BaselineChannelFeature.feature_code
    ).all()


def mark_upload_features_ready(db: Session, upload_id: UUID) -> Optional[SensorDataUpload]:
    upload = db.query(SensorDataUpload).filter(SensorDataUpload.id == upload_id).first()
    if not upload:
        return None
    upload.features_status = "ready"
    upload.features_error = None
    upload.features_computed_at = datetime.utcnow()
    db.commit()
    db.refresh(upload)
    return upload


def mark_upload_features_failed(
    db: Session, upload_id: UUID, error: str
) -> Optional[SensorDataUpload]:
    upload = db.query(SensorDataUpload).filter(SensorDataUpload.id == upload_id).first()
    if not upload:
        return None
    upload.features_status = "failed"
    upload.features_error = error
    db.commit()
    db.refresh(upload)
    return upload


# ── Threshold rule administration ───────────────────────────────────────────
#
# get_active_threshold_rules above answers "the global rules"; these answer
# "the rule that applies to this channel", which is what evaluation and the
# Settings editor both need now that rules can be scoped per channel.


def get_threshold_rules(
    db: Session,
    *,
    machine_type: Optional[str] = None,
    channel: Optional[int] = None,
    sensor_id: Optional[UUID] = None,
    include_inactive: bool = True,
) -> List[FeatureThresholdRule]:
    """Rules as stored, for administration. No fallback resolution here."""
    query = db.query(FeatureThresholdRule)
    if not include_inactive:
        query = query.filter(FeatureThresholdRule.is_active.is_(True))
    if machine_type is not None:
        query = query.filter(FeatureThresholdRule.machine_type == machine_type)
    if channel is not None:
        query = query.filter(FeatureThresholdRule.channel == channel)
    if sensor_id is not None:
        query = query.filter(FeatureThresholdRule.sensor_id == sensor_id)
    return query.order_by(
        FeatureThresholdRule.feature_code.asc(),
        FeatureThresholdRule.channel.asc().nullsfirst(),
    ).all()


def get_threshold_rule(db: Session, rule_id: UUID) -> Optional[FeatureThresholdRule]:
    return db.query(FeatureThresholdRule).filter(FeatureThresholdRule.id == rule_id).first()


def find_threshold_rule(
    db: Session,
    feature_code: str,
    *,
    channel: Optional[int] = None,
    machine_type: Optional[str] = None,
    sensor_id: Optional[UUID] = None,
    equipment_id: Optional[UUID] = None,
) -> Optional[FeatureThresholdRule]:
    """Exact scope match — used to stop a duplicate override being created.

    Every scope column is compared, including the ones left unset: a rule for
    one sensor and the global rule for the same feature are different rows at
    different scopes, and matching on feature and channel alone would report
    the global rule as a duplicate of the sensor rule and refuse to create it.
    """
    return (
        db.query(FeatureThresholdRule)
        .filter(
            FeatureThresholdRule.feature_code == feature_code,
            FeatureThresholdRule.channel.is_(None)
            if channel is None
            else FeatureThresholdRule.channel == channel,
            FeatureThresholdRule.machine_type.is_(None)
            if machine_type is None
            else FeatureThresholdRule.machine_type == machine_type,
            FeatureThresholdRule.sensor_id.is_(None)
            if sensor_id is None
            else FeatureThresholdRule.sensor_id == sensor_id,
            FeatureThresholdRule.equipment_id.is_(None)
            if equipment_id is None
            else FeatureThresholdRule.equipment_id == equipment_id,
        )
        .first()
    )


#: Scope precedence, most specific first. A limit written for one accelerometer
#: beats one written for the machine it is bolted to, which beats one written
#: for every machine of that type, which beats the factory default.
_SCOPE_SENSOR = 3
_SCOPE_EQUIPMENT = 2
_SCOPE_MACHINE_TYPE = 1
_SCOPE_GLOBAL = 0


def _scope_rank(rule: FeatureThresholdRule) -> int:
    """How narrowly this rule was written. Higher is narrower."""
    if rule.sensor_id is not None:
        return _SCOPE_SENSOR
    if rule.equipment_id is not None:
        return _SCOPE_EQUIPMENT
    if rule.machine_type is not None:
        return _SCOPE_MACHINE_TYPE
    return _SCOPE_GLOBAL


def _precedence(rule: FeatureThresholdRule) -> tuple[int, int]:
    """Higher wins: scope first, then channel within a scope.

    Scope outranks channel, which is the part that cannot be expressed by
    keying on the channel alone. A rule written for one sensor across all its
    channels is about *this machine*; a global rule naming channel 3 is about
    every machine on the platform. The sensor rule is the more specific answer
    for channel 3 even though the global one names that channel.
    """
    return (_scope_rank(rule), 1 if rule.channel is not None else 0)


def get_resolved_rule_map(
    db: Session,
    machine_type: Optional[str] = None,
    *,
    sensor_id: Optional[UUID] = None,
    equipment_id: Optional[UUID] = None,
) -> dict[tuple[Optional[int], str], FeatureThresholdRule]:
    """The rule that wins for each (channel, feature_code) in this context.

    Sensor, then equipment, then machine type, then global — and within any one
    of those, a rule naming a channel beats one that does not. Callers resolve a
    feature by trying (channel, code) and falling back to (None, code); see
    `resolve_rule`.

    Every narrowing argument left out means "no rule may be narrowed that way",
    not "any value will do". Passing no machine type therefore restricts the
    map to untyped rules, which is correct for a caller that genuinely has no
    machine — and was the live bug when the caller did have one and simply
    never passed it: the pump rules were filtered out of the map entirely, so
    no amount of configuration could make one fire.
    """
    query = db.query(FeatureThresholdRule).filter(FeatureThresholdRule.is_active.is_(True))

    # No value in hand means only rules that are not narrowed that way can
    # apply. With one, both the narrowed and the unnarrowed rules are
    # candidates and `_precedence` picks between them.
    for column, value in (
        (FeatureThresholdRule.sensor_id, sensor_id),
        (FeatureThresholdRule.equipment_id, equipment_id),
    ):
        query = query.filter(
            column.is_(None) if value is None else or_(column.is_(None), column == value)
        )

    # Machine type is compared without case or surrounding space. It is a
    # human-typed label on both sides and nothing canonicalises it: the
    # equipment records here say "Pump" and "Wind Turbine", while a rule is
    # free text a person types. Comparing them exactly would leave a rule
    # written for "pump" silently never firing, which is the same failure this
    # function was fixed for — just moved from the caller to the collation.
    if machine_type and machine_type.strip():
        query = query.filter(
            or_(
                FeatureThresholdRule.machine_type.is_(None),
                func.lower(func.trim(FeatureThresholdRule.machine_type))
                == machine_type.strip().lower(),
            )
        )
    else:
        query = query.filter(FeatureThresholdRule.machine_type.is_(None))

    rows = query.all()

    # A channel with no rule of its own is answered by the (None, code) entry,
    # so only channels some rule actually names need their own key.
    channels = sorted({row.channel for row in rows if row.channel is not None})

    resolved: dict[tuple[Optional[int], str], FeatureThresholdRule] = {}
    for channel in (*channels, None):
        for row in rows:
            if row.channel is not None and row.channel != channel:
                continue
            key = (channel, row.feature_code)
            current = resolved.get(key)
            if current is None or _precedence(row) > _precedence(current):
                resolved[key] = row
    return resolved


def resolve_rule(
    rule_map: dict[tuple[Optional[int], str], FeatureThresholdRule],
    channel: Optional[int],
    feature_code: str,
) -> Optional[FeatureThresholdRule]:
    """The rule for this channel if one is keyed, otherwise the all-channel one.

    The scope contest — sensor over equipment over machine type over global —
    is already settled by `get_resolved_rule_map`, which stores the winner
    under each key. This only has to choose between a channel that was named
    and one that was not.
    """
    return rule_map.get((channel, feature_code)) or rule_map.get((None, feature_code))
