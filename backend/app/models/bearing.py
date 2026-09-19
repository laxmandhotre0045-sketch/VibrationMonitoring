import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class BearingFaultFrequency(Base):
    """Defect frequency multipliers for a catalogued rolling-element bearing.

    The four values are *orders of running speed*, not hertz: multiply by the
    shaft speed in Hz to get the frequency to look for in a spectrum.

      FTF   fundamental train (cage) frequency
      BSF   ball spin frequency
      BPFO  ball pass frequency, outer race
      BPFI  ball pass frequency, inner race

    Imported from the manufacturers' index, one row per catalogued part. See
    `scripts/import_bearing_frequencies.py` for the source and its quirks.
    """

    __tablename__ = "bearing_fault_frequencies"

    __table_args__ = (
        # A part number is looked up either with its maker or without one, and
        # the pair is not unique — see `source_bearing_id`.
        Index("ix_bearing_freq_maker_designation", "manufacturer", "designation"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The index's own row number. Unique where (manufacturer, designation) is
    # not: the catalogue lists ~5.6k designations more than once, and 908 of
    # those are genuinely different bearings sharing a part number — usually a
    # different rolling-element count. Keeping the source id makes a row
    # traceable back to the sheet and gives the import something to key on.
    source_bearing_id = Column(Integer, nullable=False, unique=True, index=True)

    manufacturer = Column(String(16), nullable=False, index=True)
    designation = Column(String(120), nullable=False, index=True)

    # manufacturer + designation, uppercased with punctuation stripped, so
    # "SKF 6205-2RS", "skf/6205 2rs" and "SKF62052RS" all find the same row.
    search_key = Column(String(160), nullable=False, index=True)

    rolling_elements = Column(Integer, nullable=False)

    ftf = Column(Numeric(10, 4), nullable=False)
    bsf = Column(Numeric(10, 4), nullable=False)
    bpfo = Column(Numeric(10, 4), nullable=False)
    bpfi = Column(Numeric(10, 4), nullable=False)

    # Computed on import, not carried by the source. For a stationary outer
    # race BPFO + BPFI equals the rolling-element count exactly; 66 rows of the
    # catalogue break that identity and so cannot all four be right. They are
    # loaded anyway — dropping a bearing silently is worse than flagging it —
    # but a consumer should not trust them without checking the datasheet.
    is_consistent = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
