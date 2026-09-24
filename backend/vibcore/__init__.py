"""The vibration maths both services share — VIK-035.

Deterministic arithmetic only. No database, no HTTP, no LLM, and no I/O
beyond the reference tables in ``data/``. Everything here is testable
against published known answers, which is the point: neither a language
model nor a web request should ever be the thing that decides a bearing
fault frequency or an ISO severity zone.

**Why one package instead of two copies.** The platform and the chatbot
both answer questions about the same bearing on the same machine, and until
this package existed they did it from separate code. VIK-004 made that
concrete by copying ``units.py`` and ``records.py`` into the backend rather
than rewriting them -- the right call, because the conversions are checked
against published values and a second implementation drifts. But a copy is
a problem deferred: two files, one of which gets edited. The guard against
that was a test comparing the two files character by character, which is a
reasonable thing to need and a bad thing to keep needing.

The failure it was guarding against is worth naming. If the two services
disagree about BPFO for a 6205 at 1750 rpm, nothing crashes. One of them
reports a bearing fault and the other reports nothing, months apart, and
whichever a person happens to read is the answer they act on.

**Why it lives inside ``backend/``.** The backend is deployed from a Docker
build whose context is that directory, so a package anywhere else would be
invisible to the image without changing the build. The chatbot is not
containerised and installs this from the repo, so it pays nothing for the
asymmetry. The package does not import from ``app`` -- in either service --
and must not start.

What is here, and what deliberately is not:

``units``       amplitude conversion between acceleration, velocity and
                displacement, exact only at a single frequency and saying so
``records``     the audit trail every computed number carries
``bearing``     rolling-element geometry and the four defect frequencies
``iso10816``    ISO 10816-3 / 20816-3 severity zones
``signatures``  fault-signature ranking from a spectral peak list

``machine`` stays in the chatbot. It reads and writes machine profiles as
JSON files under a configured directory, which is persistence rather than
arithmetic -- and the platform keeps the same facts in a database instead.
Moving it would have brought one service's storage into the other's.
"""

from __future__ import annotations

__all__ = ["bearing", "iso10816", "records", "signatures", "units"]
