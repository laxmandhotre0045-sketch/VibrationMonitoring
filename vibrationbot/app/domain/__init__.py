"""Machine profiles — the part of the domain that is storage, not arithmetic.

The deterministic maths that used to live here moved to ``vibcore`` when
VIK-035 gave the platform and the chatbot one copy instead of two. Bearing
frequencies, ISO zones, unit conversion, fault-signature ranking and the
computation record are all imported from there now, by both services, so
they cannot drift into two different answers for the same bearing.

What is left is ``machine``: a profile registered once and reused by every
later analysis, persisted as JSON under a configured directory. That is
this service's storage, not shared arithmetic -- the platform keeps the same
facts in its database -- so moving it would have put one service's
persistence inside the other.
"""
