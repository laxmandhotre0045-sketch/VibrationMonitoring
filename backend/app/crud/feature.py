from datetime import datetime
from typing import List, Optional
from uuid import UUID

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
) -> Optional[FeatureThresholdRule]:
    """Exact scope match — used to stop a duplicate override being created."""
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
        )
        .first()
    )


def get_resolved_rule_map(
    db: Session, machine_type: Optional[str] = None
) -> dict[tuple[Optional[int], str], FeatureThresholdRule]:
    """Active rules keyed by (channel, feature_code), channel None being global.

    Callers resolve a feature by trying (channel, code) and falling back to
    (None, code); see `resolve_rule`. Machine-typed rules win over untyped ones
    at the same scope, matching get_active_threshold_rules' precedence.
    """
    query = db.query(FeatureThresholdRule).filter(FeatureThresholdRule.is_active.is_(True))
    if machine_type:
        rows = query.filter(
            FeatureThresholdRule.machine_type.in_([machine_type, None])
        ).all()
    else:
        rows = query.filter(FeatureThresholdRule.machine_type.is_(None)).all()

    resolved: dict[tuple[Optional[int], str], FeatureThresholdRule] = {}
    for row in rows:
        key = (row.channel, row.feature_code)
        current = resolved.get(key)
        # A machine-typed row beats an untyped one covering the same scope.
        if current is None or (current.machine_type is None and row.machine_type is not None):
            resolved[key] = row
    return resolved


def resolve_rule(
    rule_map: dict[tuple[Optional[int], str], FeatureThresholdRule],
    channel: Optional[int],
    feature_code: str,
) -> Optional[FeatureThresholdRule]:
    """Channel-specific rule if one exists, otherwise the global rule."""
    return rule_map.get((channel, feature_code)) or rule_map.get((None, feature_code))
