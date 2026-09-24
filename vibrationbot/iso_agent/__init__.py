"""ISO 10816-3 severity limits, answered from the unit-tested tables.

Standalone by design: it shares no state with the knowledge-base agent, loads
no document index, and needs no API key, because no language model takes part.
"""

from iso_agent.agent import IsoAnswer, IsoQuery, answer, parse_question
from iso_agent.tools import iso_zone_limits

__all__ = ["answer", "parse_question", "IsoAnswer", "IsoQuery", "iso_zone_limits"]
