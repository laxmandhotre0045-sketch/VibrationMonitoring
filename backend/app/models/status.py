"""The expert's judgement of an asset's health — SNV-STA-01, SNV-STA-10.

Status is not Priority. Priority is computed and says "look at this first";
Status is set by a person and says "this is what I think is wrong". Keeping
them apart is deliberate: a machine an analyst has already judged Critical
should stop shouting for attention, and a machine nobody has looked at is
Unknown rather than Normal.

Scoped to the two levels this schema actually has — the machine
(`equipment_masters`) and the sensor (`sensor_configurations`). The PRD's
hierarchy also names components and measuring points; `AssetScope` leaves room
for them so adding that layer later is a migration, not a rewrite.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

#: The seven values the contract publishes. Written out rather than a DB enum
#: so adding one is a code change, not a migration with a type rewrite.
STATUS_NORMAL = "Normal"
STATUS_WARNING = "Warning"
STATUS_ALARM = "Alarm"
STATUS_CRITICAL = "Critical"
STATUS_UNKNOWN = "Unknown"
STATUS_OUT_OF_SERVICE = "Out of service"
STATUS_NOT_MONITORED = "Not monitored"

STATUS_VALUES: tuple[str, ...] = (
    STATUS_NORMAL,
    STATUS_WARNING,
    STATUS_ALARM,
    STATUS_CRITICAL,
    STATUS_UNKNOWN,
    STATUS_OUT_OF_SERVICE,
    STATUS_NOT_MONITORED,
)

#: How bad each value is, for "a machine takes the worst of its sensors".
#:
#: Only the four graded states compare. Unknown means nobody has judged it and
#: must not outrank a real finding; Out of service and Not monitored are
#: statements that the machine is outside the scale entirely, so they never win
#: a comparison either — a running sensor reading Critical on a machine
#: somebody marked Out of service is still the thing worth seeing.
_SEVERITY: dict[str, int] = {
    STATUS_CRITICAL: 4,
    STATUS_ALARM: 3,
    STATUS_WARNING: 2,
    STATUS_NORMAL: 1,
    STATUS_UNKNOWN: 0,
    STATUS_OUT_OF_SERVICE: -1,
    STATUS_NOT_MONITORED: -1,
}

#: Scopes a status can be set on. "component" and "point" are not in this
#: schema yet; they are listed so the column does not have to change when the
#: hierarchy gains that layer.
SCOPE_MACHINE = "machine"
SCOPE_SENSOR = "sensor"
SCOPE_COMPONENT = "component"
SCOPE_POINT = "point"

SCOPE_VALUES: tuple[str, ...] = (SCOPE_MACHINE, SCOPE_SENSOR, SCOPE_COMPONENT, SCOPE_POINT)


def worst_status(values) -> str:
    """The most severe of several statuses, or Unknown when none compare.

    Used to roll a machine up from its sensors. Values outside the graded four
    are skipped rather than ranked, so a machine whose sensors are all
    Not monitored reports Unknown — which is true — instead of reporting the
    last value it happened to see.
    """
    graded = [v for v in values if _SEVERITY.get(v, -1) > 0]
    if not graded:
        return STATUS_UNKNOWN
    return max(graded, key=lambda v: _SEVERITY[v])


class AssetStatus(Base):
    """The current status of one asset. One row per asset, replaced in place.

    Not a history table. What changed and why lives in the clearing record
    (SNV-STA-02), which carries the finding; this row only answers "what is it
    now", which is what every screen asks.
    """

    __tablename__ = "asset_status"
    __table_args__ = (
        # One current status per asset. A second row for the same asset would
        # be two answers to a question that has one.
        UniqueConstraint("scope", "asset_id", name="uq_asset_status_scope_asset"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    #: Which kind of thing `asset_id` points at. Not a foreign key, because the
    #: target table differs by scope; the API validates that the asset exists.
    scope = Column(String(20), nullable=False)
    asset_id = Column(UUID(as_uuid=True), nullable=False)

    status = Column(String(20), nullable=False, default=STATUS_UNKNOWN)

    #: True when a person set this machine's status by hand. An overridden
    #: machine stops inheriting from its sensors — otherwise the next capture
    #: would silently undo the judgement an analyst just made.
    overridden = Column(Boolean, nullable=False, default=False)

    set_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    set_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
