from typing import Optional

from pydantic import BaseModel, ConfigDict


class BearingOut(BaseModel):
    """One catalogued bearing.

    The four frequencies are orders of running speed, not hertz: multiply by
    the shaft speed in Hz to get the line to look for in a spectrum.
    """

    model_config = ConfigDict(from_attributes=True)

    #: The catalogue's own Bearing ID — what the equipment record stores.
    source_bearing_id: int
    manufacturer: str
    designation: str
    rolling_elements: int
    ftf: float
    bsf: float
    bpfo: float
    bpfi: float
    #: False when BPFO + BPFI does not equal the rolling-element count, which
    #: means at least one of the four values in the catalogue is wrong.
    is_consistent: bool


class BearingSearchOut(BaseModel):
    items: list[BearingOut]
    count: int
    #: True when more rows matched than were returned.
    truncated: bool


class BearingResolveOut(BaseModel):
    """A lookup that is allowed to find nothing."""

    query: str
    bearing: Optional[BearingOut] = None
