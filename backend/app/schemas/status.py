"""Request and response shapes for asset status — SNV-STA-01, SNV-STA-10.

The seven values are published as a Literal so a client can switch on them
exhaustively, and so a typo is a 422 rather than a state no screen can place.
"""
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

AssetStatusValue = Literal[
    "Normal",
    "Warning",
    "Alarm",
    "Critical",
    "Unknown",
    "Out of service",
    "Not monitored",
]

AssetScope = Literal["machine", "sensor", "component", "point"]


class AssetStatusOut(BaseModel):
    scope: AssetScope
    asset_id: UUID
    status: AssetStatusValue
    #: True when a person set a machine's status by hand, so it no longer
    #: follows its sensors. Always false on a sensor, whose status is never
    #: inherited from anything.
    overridden: bool = False
    set_by: Optional[UUID] = None
    set_at: Optional[datetime] = None


class MachineStatusOut(AssetStatusOut):
    """A machine's status, with the sensors it was rolled up from.

    The sensor list travels with it so a caller can show why a machine is
    Critical without a second request — and so "inherited from a sensor" and
    "an analyst decided" are told apart on screen rather than guessed at.
    """

    sensors: List[AssetStatusOut] = Field(default_factory=list)


class AssetStatusSet(BaseModel):
    status: AssetStatusValue
    #: Setting a machine's status by hand overrides the roll-up until it is
    #: released. Ignored on a sensor.
    override: bool = True
